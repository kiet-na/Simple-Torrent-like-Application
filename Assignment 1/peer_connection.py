# peer_connection.py

import threading
import hashlib
import struct
import socket
import sys
import time

class PeerConnection(threading.Thread):
    def __init__(self, ip, port, piece_manager, peer_id, info_hash, client, sock=None, is_incoming=False):
        super().__init__()
        self.ip = ip
        self.port = port
        self.piece_manager = piece_manager
        self.peer_id = peer_id  # Local peer_id
        self.info_hash = info_hash  # Should be bytes
        self.client = client
        self.is_incoming = is_incoming
        self.running = True
        self.buffer = b''
        self.bitfield = b''
        self.remote_peer_id = None  # Store remote peer_id

        if not self.is_incoming:
            if sock is None:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                self.socket = sock
        else:
            self.socket = sock

    @classmethod
    def from_incoming(cls, client_socket, piece_manager, peer_id, info_hash, client):
        ip, port = client_socket.getpeername()
        return cls(ip, port, piece_manager, peer_id, info_hash, client, sock=client_socket, is_incoming=True)

    def run(self):
        try:
            self.perform_handshake()
            self.communicate()
        except Exception as e:
            print(f"Connection error with peer {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.socket.close()
            # Remove the peer from the connected peers list
            if self in self.client.connected_peers:
                self.client.connected_peers.remove(self)
            # Remove from connected_peer_addresses to allow reconnections
            self.client.connected_peer_addresses.discard((self.ip, self.port))
            print(f"Connection with peer {self.ip}:{self.port} closed.")

    def perform_handshake(self):
        handshake_msg = b'HELLO' + self.info_hash + self.peer_id.encode('utf-8')
        if not self.is_incoming:
            print(f"Outgoing connection to {self.ip}:{self.port}")
            self.socket.connect((self.ip, self.port))
            self.socket.sendall(handshake_msg)
            print(f"Sent handshake to {self.ip}:{self.port}")
            response = self.recvall(45)  # 'HELLO' + 20-byte info_hash + 20-byte peer_id
            if not response.startswith(b'HELLO'):
                raise Exception("Invalid handshake response")
            received_info_hash = response[5:25]
            received_peer_id = response[25:].decode('utf-8')
            if received_info_hash != self.info_hash:
                raise Exception("Info hash does not match")
            self.remote_peer_id = received_peer_id
            print(f"Connected to peer {self.ip}:{self.port} with peer_id {self.remote_peer_id}")

            # Send BITFIELD using standardized message format
            self.send_message('BITFIELD', self.piece_manager.get_bitfield())
            print(f"Sent BITFIELD to peer {self.ip}:{self.port}")

            # Receive BITFIELD from peer
            msg_type, payload = self.receive_message()
            if msg_type == 'BITFIELD':
                self.bitfield = payload
                self.piece_manager.update_piece_availability(self.bitfield)
                print(f"Received BITFIELD from peer {self.ip}:{self.port}")
        else:
            print(f"Incoming connection from {self.ip}:{self.port}")
            data = self.recvall(45)  # Receive 'HELLO' + 20-byte info_hash + 20-byte peer_id
            if not data.startswith(b'HELLO'):
                raise Exception("Invalid handshake message")
            received_info_hash = data[5:25]
            received_peer_id = data[25:].decode('utf-8')
            if received_info_hash != self.info_hash:
                raise Exception("Info hash does not match")
            self.remote_peer_id = received_peer_id
            self.socket.sendall(handshake_msg)
            print(f"Accepted connection from {self.ip}:{self.port} with peer_id {self.remote_peer_id}")

            # Receive BITFIELD from peer
            msg_type, payload = self.receive_message()
            if msg_type == 'BITFIELD':
                self.bitfield = payload
                self.piece_manager.update_piece_availability(self.bitfield)
                print(f"Received BITFIELD from peer {self.ip}:{self.port}")

            # Send BITFIELD using standardized message format
            self.send_message('BITFIELD', self.piece_manager.get_bitfield())
            print(f"Sent BITFIELD to peer {self.ip}:{self.port}")

    def communicate(self):
        if self.client.role == 'leecher':
            # Leecher behavior: request pieces
            print("Leecher: Starting communicate loop.")
            while self.running and not self.piece_manager.is_complete():
                piece_index = self.client.request_piece_from_rarest()
                if piece_index is None:
                    print("Leecher: No more pieces to request.")
                    break  # All pieces downloaded
                if piece_index in self.piece_manager.requested_pieces:
                    continue  # Already requested
                # Request the piece
                self.piece_manager.requested_pieces.add(piece_index)
                self.request_piece(piece_index)
                # Wait for the piece
                print(f"Leecher: Waiting for PIECE {piece_index}")
                try:
                    msg_type, payload = self.receive_message()
                    if msg_type == 'PIECE':
                        received_piece_index, piece_data = self.parse_piece(payload)
                        self.piece_manager.add_piece(received_piece_index, piece_data)
                        print(f"Leecher: Received Piece {received_piece_index} from peer {self.ip}:{self.port}")
                        # Notify the client that a new piece has been downloaded
                        self.client.notify_piece_downloaded(received_piece_index)
                except Exception as e:
                    print(f"Leecher: Error receiving PIECE - {e}")
                    # Requeue the piece for future requests
                    self.piece_manager.requested_pieces.discard(piece_index)
                    with self.client.request_lock:
                        priority = self.piece_manager.piece_availability[piece_index]
                        self.client.request_queue.put((priority, piece_index))
                    break  # Exit the loop on error
            print(f"Leecher: Download complete from peer {self.ip}:{self.port}")
        elif self.client.role == 'seeder':
            # Seeder behavior: respond to piece requests
            print("Seeder: Starting communicate loop.")
            while self.running:
                try:
                    msg_type, payload = self.receive_message()
                    if msg_type == 'REQUEST':
                        piece_index = struct.unpack('!I', payload[:4])[0]  # 4-byte piece index
                        print(f"Seeder: Processing REQUEST for piece {piece_index}")
                        piece_data = self.piece_manager.get_piece(piece_index)
                        if piece_data:
                            # Send PIECE message and increment uploaded
                            self.send_piece(piece_index, piece_data)
                            print(f"Seeder: Sent PIECE {piece_index} to peer {self.ip}:{self.port}")
                            with self.piece_manager.lock:
                                self.piece_manager.uploaded += len(piece_data)
                        else:
                            print(f"Seeder: Piece {piece_index} requested by peer {self.ip}:{self.port} not available.")
                except Exception as e:
                    print(f"Seeder: Error in communication with peer {self.ip}:{self.port} - {e}")
                    break
            print(f"Seeder: Communication with peer {self.ip}:{self.port} ended.")

    def send_message(self, msg_type, payload):
        """
        Standardized message format:
        [4-byte length][8-byte type][payload]
        """
        msg_type_padded = msg_type.ljust(8).encode('utf-8')
        msg_length = 8 + len(payload)
        msg = struct.pack('!I', msg_length) + msg_type_padded + payload
        self.socket.sendall(msg)
        print(f"Sent {msg_type} to {self.ip}:{self.port}")

    def receive_message(self):
        """
        Receive messages following the standardized format.
        """
        length_bytes = self.recvall(4)
        if not length_bytes:
            raise Exception("Connection closed by peer.")
        length = struct.unpack('!I', length_bytes)[0]
        msg_type_bytes = self.recvall(8)
        if not msg_type_bytes:
            raise Exception("Connection closed by peer.")
        msg_type = msg_type_bytes.decode('utf-8').strip()
        payload_length = length - 8
        payload = self.recvall(payload_length)
        print(f"DEBUG: Received {msg_type} with payload length {payload_length} from {self.ip}:{self.port}")
        return msg_type, payload

    def request_piece(self, piece_index):
        """
        Send a REQUEST message for the specified piece_index.
        """
        self.send_message('REQUEST', piece_index)
        print(f"Requested Piece {piece_index} from peer {self.ip}:{self.port}")

    def parse_piece(self, payload):
        if len(payload) < 4:
            raise Exception("Invalid PIECE payload length.")
        piece_index = struct.unpack('!I', payload[:4])[0]
        piece_data = payload[4:]
        print(f"Parsed PIECE {piece_index} with {len(piece_data)} bytes.")
        return piece_index, piece_data

    def recvall(self, n):
        """
        Helper function to receive exactly n bytes or raise an exception.
        """
        data = b''
        while len(data) < n:
            packet = self.socket.recv(n - len(data))
            if not packet:
                raise Exception("Connection closed by peer during message reception.")
            data += packet
        return data

    def send_piece(self, piece_index, piece_data):
        try:
            piece_index_bytes = struct.pack('!I', piece_index)
            payload = piece_index_bytes + piece_data
            self.send_message('PIECE', payload)
            with self.piece_manager.lock:
                self.piece_manager.uploaded += len(piece_data)
            print(f"Uploaded piece {piece_index} to {self.ip}:{self.port}")
        except Exception as e:
            print(f"Error sending piece {piece_index} to {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()

