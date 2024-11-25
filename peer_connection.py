# peer_connection.py

import threading
import socket
import queue
class PeerConnection(threading.Thread):
    def __init__(self, ip, port, piece_manager, peer_id, info_hash, client):
        super().__init__()
        self.ip = ip
        self.port = port
        self.piece_manager = piece_manager
        self.peer_id = peer_id
        self.info_hash = info_hash
        self.client = client  # Reference to NodeClient
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_incoming = False
        self.peer_bitfield = None

    @classmethod
    def from_incoming(cls, client_socket, piece_manager, peer_id, info_hash, client):
        instance = cls(None, None, piece_manager, peer_id, info_hash, client)
        instance.socket = client_socket
        instance.is_incoming = True
        instance.ip, instance.port = client_socket.getpeername()
        return instance

    def run(self):
        try:
            if not self.is_incoming:
                print(f"Outgoing connection to {self.ip}:{self.port}")
                self.socket.connect((self.ip, self.port))
            else:
                print(f"Incoming connection from {self.ip}:{self.port}")
            # Perform handshake and communication
            self.perform_handshake()
            self.communicate()
            self.display_statistics()
        except Exception as e:
            print(f"Connection error with peer {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.socket.close()

    def perform_handshake(self):
        handshake_msg = b'HELLO' + self.info_hash.encode('utf-8') + self.peer_id.encode('utf-8')
        if not self.is_incoming:
            # Outgoing connection, send handshake
            self.socket.sendall(handshake_msg)
            # Receive handshake
            response = self.socket.recv(68)
            if not response.startswith(b'HELLO'):
                raise Exception("Invalid handshake response")
            # Send our bitfield
            self.send_bitfield()
            # Receive peer's bitfield
            data = self.socket.recv(1024)
            if data.startswith(b'BITFIELD'):
                self.receive_bitfield(data)
        else:
            # Incoming connection, receive handshake
            data = self.socket.recv(68)
            if not data.startswith(b'HELLO'):
                raise Exception("Invalid handshake message")
            # Send handshake response
            self.socket.sendall(handshake_msg)
            # Receive peer's bitfield
            data = self.socket.recv(1024)
            if data.startswith(b'BITFIELD'):
                self.receive_bitfield(data)
            # Send our bitfield
            self.send_bitfield()

    def send_bitfield(self):
        bitfield = self.piece_manager.get_bitfield()
        msg = b'BITFIELD' + bitfield
        self.socket.sendall(msg)

    def receive_bitfield(self, data):
        self.peer_bitfield = data[len(b'BITFIELD'):]
        self.piece_manager.update_piece_availability(self.peer_bitfield)

    def communicate(self):
        try:
            # Start requesting pieces
            if not self.is_incoming:
                self.request_pieces_from_peer()
            # Handle incoming requests and responses
            while True:
                data = self.socket.recv(9)
                if not data:
                    break
                if data.startswith(b'REQUEST'):
                    piece_index = int.from_bytes(data[7:], byteorder='big')
                    self.send_piece(piece_index)
                elif data.startswith(b'PIECE'):
                    self.receive_piece(data)
                else:
                    print(f"Unknown message from {self.ip}:{self.port}: {data}")
        except Exception as e:
            print(f"Communication error with peer {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()

    def receive_piece(self, data):
        piece_index = int.from_bytes(data[5:7], byteorder='big')
        piece_data = data[7:]
        self.piece_manager.add_piece(piece_index, piece_data)
        print(f"Received piece {piece_index} from {self.ip}:{self.port}")
    def request_pieces_from_peer(self):
        while not self.piece_manager.is_complete():
            try:
                piece_index = self.client.request_queue.get(timeout=10)
                if not self.has_piece(piece_index):
                    self.client.request_queue.put(piece_index)
                    continue
                if piece_index in self.piece_manager.requested_pieces:
                    continue  # Already requested
                self.piece_manager.requested_pieces.add(piece_index)
                self.request_piece(piece_index)
                self.client.request_queue.task_done()
            except queue.Empty:
                break  # No more pieces to request

    def has_piece(self, index):
        byte_index = index // 8
        bit_index = index % 8
        if self.peer_bitfield is None:
            return False
        if byte_index >= len(self.peer_bitfield):
            return False
        return (self.peer_bitfield[byte_index] >> (7 - bit_index)) & 1

    def request_piece(self, piece_index):
        try:
            request_msg = b'REQUEST' + piece_index.to_bytes(2, byteorder='big')
            self.socket.sendall(request_msg)
            response = self.socket.recv(5)
            if response == b'PIECE':
                index_bytes = self.socket.recv(2)
                received_piece_index = int.from_bytes(index_bytes, byteorder='big')
                # Determine expected piece length
                # Existing code to receive piece data...
                piece_data = b''
                expected_length = self.piece_manager.get_piece_length(received_piece_index)
                while len(piece_data) < expected_length:
                    data = self.socket.recv(4096)
                    if not data:
                        break
                    piece_data += data
                self.piece_manager.add_piece(received_piece_index, piece_data)
                print(f"Downloaded piece {received_piece_index} from {self.ip}:{self.port}")
            else:
                print(f"Unexpected response from {self.ip}:{self.port}: {response}")
            self.piece_manager.requested_pieces.discard(piece_index)
        except Exception as e:
            print(f"Error requesting piece {piece_index} from {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()
            self.piece_manager.requested_pieces.discard(piece_index)
            self.client.request_queue.put(piece_index)  # Requeue the piece

    def send_piece(self, piece_index):
        try:
            piece_data = self.piece_manager.get_piece(piece_index)
            if piece_data is not None:
                response = b'PIECE'
                self.socket.sendall(response)
                self.socket.sendall(piece_index.to_bytes(2, byteorder='big'))
                self.socket.sendall(piece_data)
                self.piece_manager.uploaded += len(piece_data)
                print(f"Uploaded piece {piece_index} to {self.ip}:{self.port}")
            else:
                print(f"Piece {piece_index} not available.")
            self.display_statistics()
        except Exception as e:
            print(f"Error sending piece {piece_index} to {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()
    def display_statistics(self):
        print(f"Downloaded: {self.piece_manager.downloaded} bytes")
        print(f"Uploaded: {self.piece_manager.uploaded} bytes")