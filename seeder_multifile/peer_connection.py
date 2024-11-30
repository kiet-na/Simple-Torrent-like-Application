# peer_connection.py

import threading
import hashlib
import struct
import socket
import sys
import time
MAX_CONCURRENT_REQUESTS = 5  # Example limit
MESSAGE_CHOKE = 0
MESSAGE_UNCHOKE = 1
MESSAGE_INTERESTED = 2
MESSAGE_NOT_INTERESTED = 3
MESSAGE_HAVE = 4
MESSAGE_BITFIELD = 5
MESSAGE_REQUEST = 6
MESSAGE_PIECE = 7
MESSAGE_CANCEL = 8

class PeerConnection(threading.Thread):
    def __init__(self, ip, port, piece_manager, peer_id, info_hash, client, sock=None, is_incoming=False, verbose=False):
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
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.verbose = verbose
        self.current_requests = 0
        if not self.is_incoming:
            if sock is None:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                self.socket = sock
        else:
            self.socket = sock

    @classmethod
    def from_incoming(cls, client_socket, piece_manager, peer_id, info_hash, client, verbose=False):
        ip, port = client_socket.getpeername()
        return cls(ip, port, piece_manager, peer_id, info_hash, client, sock=client_socket, is_incoming=True, verbose=verbose)

    def run(self):
        try:
            self.perform_handshake()
            self.communicate()
        except Exception as e:
            if self.verbose:
                print(f"Connection error with peer {self.ip}:{self.port} - {e}")
        finally:
            self.socket.close()
            # Remove the peer from the connected peers list
            if self in self.client.connected_peers:
                self.client.connected_peers.remove(self)
            # Remove from connected_peer_addresses to allow reconnections
            self.client.connected_peer_addresses.discard((self.ip, self.port))
            if self.verbose:
                print(f"Connection with peer {self.ip}:{self.port} closed.")

    def perform_handshake(self):
        pstr = 'BitTorrent protocol'
        pstrlen = len(pstr)
        reserved = b'\x00' * 8
        handshake_msg = struct.pack('!B', pstrlen) + pstr.encode('utf-8') + reserved + self.info_hash + self.peer_id.encode('utf-8')

        if not self.is_incoming:
            if self.verbose:
                print(f"Outgoing connection to {self.ip}:{self.port}")
            self.socket.connect((self.ip, self.port))
            self.socket.sendall(handshake_msg)
            if self.verbose:
                print(f"Sent handshake to {self.ip}:{self.port}")
            response = self.recvall(68)  # Handshake message is 68 bytes
            if len(response) < 68:
                raise Exception("Invalid handshake response")
            received_pstrlen = response[0]
            received_pstr = response[1:1 + received_pstrlen]
            received_info_hash = response[1 + pstrlen + 8:1 + pstrlen + 8 + 20]
            received_peer_id = response[1 + pstrlen + 8 + 20:].decode('utf-8', errors='ignore')

            if received_info_hash != self.info_hash:
                raise Exception("Info hash does not match")
            self.remote_peer_id = received_peer_id
            if self.verbose:
                print(f"Connected to peer {self.ip}:{self.port} with peer_id {self.remote_peer_id}")

            # Send BITFIELD
            bitfield = self.piece_manager.get_bitfield()
            if bitfield:
                self.send_message(MESSAGE_BITFIELD, bitfield)
                if self.verbose:
                    print(f"Sent BITFIELD to peer {self.ip}:{self.port}")

        else:
            if self.verbose:
                print(f"Incoming connection from {self.ip}:{self.port}")
            data = self.recvall(68)
            if len(data) < 68:
                raise Exception("Invalid handshake message")
            received_pstrlen = data[0]
            received_pstr = data[1:1 + received_pstrlen]
            received_info_hash = data[1 + received_pstrlen + 8:1 + received_pstrlen + 8 + 20]
            received_peer_id = data[1 + received_pstrlen + 8 + 20:].decode('utf-8', errors='ignore')

            if received_info_hash != self.info_hash:
                raise Exception("Info hash does not match")
            self.remote_peer_id = received_peer_id

            # Send handshake
            self.socket.sendall(handshake_msg)
            if self.verbose:
                print(f"Accepted connection from {self.ip}:{self.port} with peer_id {self.remote_peer_id}")

            # Receive BITFIELD
            msg_id, payload = self.receive_message()
            if msg_id == MESSAGE_BITFIELD:
                self.bitfield = payload
                self.piece_manager.update_piece_availability(self.bitfield)
                if self.verbose:
                    print(f"Received BITFIELD from peer {self.ip}:{self.port}")

        # Send our BITFIELD after handshake
        bitfield = self.piece_manager.get_bitfield()
        if bitfield:
            self.send_message(MESSAGE_BITFIELD, bitfield)
            if self.verbose:
                print(f"Sent BITFIELD to peer {self.ip}:{self.port}")

    def keep_alive(self):
        while self.running:
            time.sleep(120)  # Send keep-alive every 2 minutes
            try:
                self.socket.sendall(struct.pack('!I', 0))
                if self.verbose:
                    print(f"Sent keep-alive to {self.ip}:{self.port}")
            except Exception as e:
                if self.verbose:
                    print(f"Error sending keep-alive to {self.ip}:{self.port} - {e}")
                break

    def communicate(self):
        # Start a thread to send keep-alive messages if needed
        threading.Thread(target=self.keep_alive, daemon=True).start()

        # After handshake, update interest state
        self.update_interest()

        while self.running:
            try:
                msg_id, payload = self.receive_message()
                if msg_id is None:
                    continue  # Keep-alive
                self.handle_message(msg_id, payload)
            except Exception as e:
                if self.verbose:
                    print(f"Error in communication with peer {self.ip}:{self.port} - {e}")
                break

    def send_message(self, msg_id, payload=b''):
        try:
            # Implement upload speed limiting if needed
            msg_length = 1 + len(payload)
            msg = struct.pack('!I', msg_length) + struct.pack('!B', msg_id) + payload
            self.socket.sendall(msg)
            if self.verbose:
                print(f"Sent message ID {msg_id} to {self.ip}:{self.port}")
        except Exception as e:
            if self.verbose:
                print(f"Failed to send message ID {msg_id} to {self.ip}:{self.port} - {e}")
            self.running = False

    def receive_message(self):
        length_bytes = self.recvall(4)
        if not length_bytes:
            raise Exception("Connection closed")
        length = struct.unpack('!I', length_bytes)[0]
        if length == 0:
            # Keep-alive message
            return None, None
        msg_id_bytes = self.recvall(1)
        if not msg_id_bytes:
            raise Exception("Connection closed")
        msg_id = struct.unpack('!B', msg_id_bytes)[0]
        payload_length = length - 1
        payload = self.recvall(payload_length) if payload_length > 0 else b''
        return msg_id, payload

    def recvall(self, n):
        data = b''
        while len(data) < n:
            packet = self.socket.recv(n - len(data))
            if not packet:
                raise Exception("Connection closed")
            data += packet
        return data

    def handle_message(self, msg_id, payload):
        if msg_id == MESSAGE_CHOKE:
            self.peer_choking = True
            if self.verbose:
                print(f"Peer {self.ip}:{self.port} choked us.")
        elif msg_id == MESSAGE_UNCHOKE:
            self.peer_choking = False
            if self.verbose:
                print(f"Peer {self.ip}:{self.port} unchoked us.")
            # Start requesting pieces if interested
            if self.am_interested:
                self.request_pieces()
        elif msg_id == MESSAGE_INTERESTED:
            self.peer_interested = True
            if self.verbose:
                print(f"Peer {self.ip}:{self.port} is interested.")
            # Decide whether to unchoke the peer
            self.manage_choking()
        elif msg_id == MESSAGE_NOT_INTERESTED:
            self.peer_interested = False
            if self.verbose:
                print(f"Peer {self.ip}:{self.port} is not interested.")
        elif msg_id == MESSAGE_HAVE:
            piece_index = struct.unpack('!I', payload)[0]
            self.piece_manager.update_piece_availability_for_piece(piece_index)
            if self.verbose:
                print(f"Peer {self.ip}:{self.port} has piece {piece_index}.")
            # Update interest
            self.update_interest()
        elif msg_id == MESSAGE_BITFIELD:
            self.bitfield = payload
            self.piece_manager.update_piece_availability(self.bitfield)
            if self.verbose:
                print(f"Received BITFIELD from peer {self.ip}:{self.port}.")
            # Update interest
            self.update_interest()
        elif msg_id == MESSAGE_REQUEST:
            self.handle_request(payload)
        elif msg_id == MESSAGE_PIECE:
            self.handle_piece(payload)
        elif msg_id == MESSAGE_CANCEL:
            # Handle cancel if necessary
            pass
        else:
            if self.verbose:
                print(f"Unknown message ID: {msg_id}")

    def request_pieces(self):
        while (not self.piece_manager.is_complete() and
               self.am_interested and
               not self.peer_choking and
               self.current_requests < MAX_CONCURRENT_REQUESTS):
            piece_index = self.client.request_piece_from_rarest()
            if piece_index is None:
                break
            if not self.has_piece_in_bitfield(self.bitfield, piece_index):
                if self.verbose:
                    print(f"Peer {self.ip}:{self.port} does not have piece {piece_index}. Skipping.")
                continue
            # Define the begin and length
            begin = 0
            length = self.piece_manager.get_piece_length(piece_index)
            # Send request message
            payload = struct.pack('!III', piece_index, begin, length)
            self.send_message(MESSAGE_REQUEST, payload)
            self.current_requests += 1
            if self.verbose:
                print(f"Requested piece {piece_index} from {self.ip}:{self.port}")

    def has_piece_in_bitfield(self, bitfield, index):
        byte_index = index // 8
        bit_index = index % 8
        if byte_index >= len(bitfield):
            return False
        return (bitfield[byte_index] >> (7 - bit_index)) & 1

    def has_piece(self, index):
        return self.piece_manager.has_piece(index)

    def handle_piece(self, payload):
        piece_index, begin = struct.unpack('!II', payload[:8])
        block = payload[8:]
        if self.verbose:
            print(f"Handling Piece {piece_index} (Begin: {begin}, Length: {len(block)})")
        self.piece_manager.add_piece(piece_index, begin, block)
        if self.verbose:
            print(f"Received piece {piece_index} (offset {begin}) from {self.ip}:{self.port}")

        # Check if the piece is complete and verified
        if self.piece_manager.is_piece_complete(piece_index):
            self.client.notify_piece_downloaded(piece_index)
            if self.verbose:
                print(f"Piece {piece_index} is complete and verified.")
            # Update interest
            self.update_interest()
            # Potentially request more pieces
            if not self.peer_choking:
                self.request_pieces()
                self.current_requests -= 1

    def handle_request(self, payload):
        piece_index, begin, length = struct.unpack('!III', payload)
        if not self.am_choking and self.has_piece(piece_index):
            self.send_piece(piece_index, begin, length)
            if self.verbose:
                print(f"Sent piece {piece_index} to peer {self.ip}:{self.port}")
        else:
            if self.verbose:
                print(
                    f"Cannot send piece {piece_index} to peer {self.ip}:{self.port} because we are choking or don't have the piece.")

    def send_piece(self, piece_index, begin, length):
        try:
            piece_data = self.piece_manager.get_piece(piece_index)
            if piece_data is not None:
                block = piece_data[begin:begin + length]
                payload = struct.pack('!II', piece_index, begin) + block
                self.send_message(MESSAGE_PIECE, payload)
                self.piece_manager.uploaded += len(block)
                if self.verbose:
                    print(f"Uploaded piece {piece_index} (offset {begin}) to {self.ip}:{self.port}. Total uploaded: {self.piece_manager.uploaded} bytes.")
            else:
                if self.verbose:
                    print(f"Piece {piece_index} not available.")
        except Exception as e:
            if self.verbose:
                print(f"Error sending piece {piece_index} to {self.ip}:{self.port} - {e}")

    def manage_choking(self):
        # Simple policy: unchoke interested peers
        if self.peer_interested and self.am_choking:
            self.am_choking = False
            self.send_message(MESSAGE_UNCHOKE)
            if self.verbose:
                print(f"Unchoked peer {self.ip}:{self.port}")
        elif not self.peer_interested and not self.am_choking:
            self.am_choking = True
            self.send_message(MESSAGE_CHOKE)
            if self.verbose:
                print(f"Choked peer {self.ip}:{self.port}")

    def update_interest(self):
        # Check if we are interested in any pieces the peer has
        if self.has_pieces_of_interest():
            if not self.am_interested:
                self.am_interested = True
                self.send_message(MESSAGE_INTERESTED)
                if self.verbose:
                    print(f"Sent INTERESTED to {self.ip}:{self.port}")
        else:
            if self.am_interested:
                self.am_interested = False
                self.send_message(MESSAGE_NOT_INTERESTED)
                if self.verbose:
                    print(f"Sent NOT INTERESTED to {self.ip}:{self.port}")

    def has_pieces_of_interest(self):
        for index in self.piece_manager.missing_pieces:
            if self.has_piece_in_bitfield(self.bitfield, index):
                return True
        return False
