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
            self.exchange_bitfield()
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
            response = self.recvall(45)  # 'HELLO' + 20-byte info_hash + 8-byte peer_id (assuming 8-byte peer_id)
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
            data = self.recvall(45)  # Receive 'HELLO' + 20-byte info_hash + 8-byte peer_id
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

    def exchange_bitfield(self):
        # This method is now redundant as BITFIELD exchange is handled in perform_handshake
        pass

    def communicate(self):
        if self.client.role == 'leecher':
            # Leecher behavior: request pieces
            print("Leecher: Starting communicate loop.")
            while self.running and not self.piece_manager.is_complete():
                piece_index = self.piece_manager.next_missing_piece()
                print(f"Leecher: next_missing_piece() returned {piece_index}")
                if piece_index is None:
                    break  # All pieces downloaded
                # Request the piece
                self.request_piece(piece_index)
                # Wait for the piece
                print(f"Leecher: Waiting for PIECE {piece_index}")
                try:
                    msg_type, payload = self.receive_message()
                    print(f"Leecher: Received message type {msg_type}")
                    if msg_type == 'PIECE':
                        received_piece_index, piece_data = self.parse_piece(payload)
                        self.piece_manager.add_piece(received_piece_index, piece_data)
                        print(f"Leecher: Received Piece {received_piece_index} from peer {self.ip}:{self.port}")
                except Exception as e:
                    print(f"Leecher: Error receiving PIECE - {e}")
                    break
            print(f"Leecher: Download complete from peer {self.ip}:{self.port}")
        elif self.client.role == 'seeder':
            # Seeder behavior: respond to piece requests
            print("Seeder: Starting communicate loop.")
            while self.running:
                try:
                    msg_type, payload = self.receive_message()
                    print(f"Seeder: Received message type {msg_type}")
                    if msg_type == 'REQUEST':
                        piece_index = struct.unpack('!I', payload[:4])[0]  # 4-byte piece index
                        print(f"Seeder: Processing REQUEST for piece {piece_index}")
                        piece_data = self.piece_manager.get_piece(piece_index)
                        if piece_data:
                            # Send PIECE message and increment uploaded
                            self.send_piece(piece_index)
                            print(f"Seeder: Sent PIECE {piece_index} to peer {self.ip}:{self.port}")
                        else:
                            print(f"Seeder: Piece {piece_index} requested by peer {self.ip}:{self.port} not available.")
                except Exception as e:
                    print(f"Seeder: Error in communication with peer {self.ip}:{self.port} - {e}")
                    break
            print(f"Seeder: Communication with peer {self.ip}:{self.port} ended.")

    def send_message(self, msg_type, payload):
        if msg_type == 'BITFIELD':
            msg_type_padded = msg_type.ljust(8).encode('utf-8')
            msg_length = 8 + len(payload)
            msg = struct.pack('!I', msg_length) + msg_type_padded + payload
            self.socket.sendall(msg)
            print(f"Sent BITFIELD to {self.ip}:{self.port}")
        elif msg_type == 'REQUEST':
            # Message format: [4-byte length][8-byte type][4-byte piece_index]
            msg_type_padded = msg_type.ljust(8).encode('utf-8')
            msg_length = 8 + 4  # 8-byte type + 4-byte piece index
            msg = struct.pack('!I', msg_length) + msg_type_padded + struct.pack('!I', payload)
            self.socket.sendall(msg)
            print(f"Sent REQUEST for piece {payload} to {self.ip}:{self.port}")
        elif msg_type == 'PIECE':
            # Message format: [4-byte length][8-byte type][4-byte piece_index][piece_data]
            msg_type_padded = msg_type.ljust(8).encode('utf-8')
            msg_length = 8 + len(payload)  # 8-byte type + payload
            msg = struct.pack('!I', msg_length) + msg_type_padded + payload
            self.socket.sendall(msg)
            print(f"Sent PIECE to {self.ip}:{self.port}")
        else:
            print(f"Unknown message type: {msg_type}")

    def receive_message(self):
        length_bytes = self.recvall(4)
        if not length_bytes:
            raise Exception("Connection closed")
        length = struct.unpack('!I', length_bytes)[0]
        msg_type_bytes = self.recvall(8)
        if not msg_type_bytes:
            raise Exception("Connection closed")
        msg_type = msg_type_bytes.decode('utf-8').strip()
        payload_length = length - 8
        payload = self.recvall(payload_length)
        return msg_type, payload

    def request_piece(self, piece_index):
        if piece_index in self.piece_manager.requested_pieces:
            print(f"Piece {piece_index} already requested from peer {self.ip}:{self.port}")
            return  # Already requested
        self.piece_manager.requested_pieces.add(piece_index)
        self.send_message('REQUEST', piece_index)
        print(f"Requested Piece {piece_index} from peer {self.ip}:{self.port}")

    def parse_piece(self, payload):
        # Assuming payload starts with 4-byte piece index followed by piece data
        if len(payload) < 4:
            raise Exception("Invalid PIECE payload")
        piece_index = struct.unpack('!I', payload[:4])[0]
        piece_data = payload[4:]
        return piece_index, piece_data

    def recvall(self, n):
        data = b''
        while len(data) < n:
            packet = self.socket.recv(n - len(data))
            if not packet:
                break
            data += packet
        return data

    def send_piece(self, piece_index):
        try:
            piece_data = self.piece_manager.get_piece(piece_index)
            if piece_data is not None:
                piece_payload = struct.pack('!I', piece_index) + piece_data
                self.send_message('PIECE', piece_payload)
                self.piece_manager.uploaded += len(piece_data)
                print(f"Uploaded piece {piece_index} to {self.ip}:{self.port}")
        except Exception as e:
            print(f"Error sending piece {piece_index} to {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()

    def display_statistics(self):
        print(f"Downloaded: {self.piece_manager.downloaded} bytes")
        print(f"Uploaded: {self.piece_manager.uploaded} bytes")

    # peer_connection.py

    def handle_messages(self):
        while self.running:
            try:
                msg_id, payload = self.receive_message()
                if msg_id is None:
                    continue  # Keep-alive
                elif msg_id == 0:  # Choke
                    self.peer_choking = True
                elif msg_id == 1:  # Unchoke
                    self.peer_choking = False
                    # Start requesting pieces
                    if self.client.role == 'leecher':
                        self.request_pieces()
                elif msg_id == 2:  # Interested
                    self.peer_interested = True
                elif msg_id == 3:  # Not Interested
                    self.peer_interested = False
                elif msg_id == 4:  # Have
                    piece_index = struct.unpack('>I', payload)[0]
                    self.update_peer_bitfield(piece_index)
                elif msg_id == 5:  # Bitfield
                    self.peer_bitfield = payload
                    self.piece_manager.update_piece_availability(self.peer_bitfield)
                elif msg_id == 6:  # Request
                    if self.client.role == 'seeder':
                        self.handle_request(payload)
                elif msg_id == 7:  # Piece
                    self.handle_piece(payload)
                elif msg_id == 8:  # Cancel
                    # Handle cancel if necessary
                    pass
                else:
                    print(f"Unknown message ID: {msg_id}")
            except Exception as e:
                print(f"Error handling messages: {e}")
                break

    def request_pieces(self):
        pipeline_size = 5  # Number of outstanding requests
        while not self.piece_manager.is_complete():
            if self.peer_choking:
                break  # Cannot request when choked
            while len(self.piece_manager.requested_pieces) < pipeline_size:
                piece_index = self.piece_manager.next_missing_piece()
                if piece_index is None:
                    break
                if not self.has_piece(piece_index):
                    continue
                self.piece_manager.requested_pieces.add(piece_index)
                # Send request message
                payload = struct.pack('>III', piece_index, 0, self.piece_manager.get_piece_length(piece_index))
                self.send_message(6, payload)
                print(f"Requested piece {piece_index} from {self.ip}:{self.port}")
            # Wait for incoming messages
            msg_id, payload = self.receive_message()
            if msg_id == 7:  # Piece
                self.handle_piece(payload)
            elif msg_id == 0:  # Choke
                self.peer_choking = True
                break
            else:
                # Handle other messages
                pass

    def handle_piece(self, payload):
        index, begin = struct.unpack('>II', payload[:8])
        block = payload[8:]
        self.piece_manager.add_piece_block(index, begin, block)
        print(f"Received piece {index} from {self.ip}:{self.port}")

    def handle_request(self, payload):
        index, begin, length = struct.unpack('>III', payload)
        piece_data = self.piece_manager.get_piece_block(index, begin, length)
        if piece_data:
            # Send piece message
            piece_payload = struct.pack('>II', index, begin) + piece_data
            self.send_message(7, piece_payload)
            print(f"Sent piece {index} to {self.ip}:{self.port}")
        else:
            print(f"Piece {index} not available")

    def manage_choking(self):
        # Simple policy: unchoke all peers
        self.send_message(1)  # Unchoke
        self.peer_choking = False

    def update_interest(self):
        if self.client.role == 'leecher':
            if self.has_pieces_of_interest():
                self.send_message(2)  # Interested
            else:
                self.send_message(3)  # Not Interested

    def has_pieces_of_interest(self):
        for index in self.piece_manager.missing_pieces:
            if self.has_piece(index):
                return True
        return False
