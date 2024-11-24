# peer_connection.py

import threading
import socket
import hashlib

class PeerConnection(threading.Thread):
    def __init__(self, ip, port, piece_manager, peer_id, info_hash):
        super().__init__()
        self.ip = ip
        self.port = port
        self.piece_manager = piece_manager
        self.peer_id = peer_id
        self.info_hash = info_hash
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_incoming = False

    @classmethod
    def from_incoming(cls, client_socket, piece_manager, peer_id, info_hash):
        instance = cls(None, None, piece_manager, peer_id, info_hash)
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
            response = self.socket.recv(68)  # Adjusted length
            if not response.startswith(b'HELLO'):
                raise Exception("Invalid handshake response")
        else:
            # Incoming connection, receive handshake
            data = self.socket.recv(68)
            if not data.startswith(b'HELLO'):
                raise Exception("Invalid handshake message")
            # Send handshake response
            handshake_msg = b'HELLO' + self.info_hash.encode('utf-8') + self.peer_id.encode('utf-8')
            self.socket.sendall(handshake_msg)

    def communicate(self):
        try:
            if not self.is_incoming:
                # Leecher requesting pieces
                while not self.piece_manager.is_complete():
                    piece_index = self.piece_manager.next_missing_piece()
                    if piece_index is not None:
                        self.request_piece(piece_index)
                    else:
                        break
            else:
                # Seeder handling requests
                while True:
                    data = self.socket.recv(9)
                    if not data:
                        break
                    if data.startswith(b'REQUEST'):
                        piece_index = int.from_bytes(data[7:], byteorder='big')
                        self.send_piece(piece_index)
                    else:
                        print(f"Unknown message from {self.ip}:{self.port}: {data}")
        except Exception as e:
            print(f"Communication error with peer {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()

    def request_piece(self, piece_index):
        try:
            request_msg = b'REQUEST' + piece_index.to_bytes(2, byteorder='big')
            self.socket.sendall(request_msg)
            response = self.socket.recv(5)
            if response == b'PIECE':
                index_bytes = self.socket.recv(2)
                received_piece_index = int.from_bytes(index_bytes, byteorder='big')

                # Determine expected piece length
                if received_piece_index == self.piece_manager.total_pieces - 1:
                    expected_length = self.piece_manager.total_length - received_piece_index * self.piece_manager.piece_length
                else:
                    expected_length = self.piece_manager.piece_length

                piece_data = b''
                while len(piece_data) < expected_length:
                    data = self.socket.recv(4096)
                    if not data:
                        break
                    piece_data += data

                self.piece_manager.add_piece(received_piece_index, piece_data)
                print(f"Downloaded piece {received_piece_index} from {self.ip}:{self.port}")
            else:
                print(f"Unexpected response from {self.ip}:{self.port}: {response}")
        except Exception as e:
            print(f"Error requesting piece {piece_index} from {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()

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
        except Exception as e:
            print(f"Error sending piece {piece_index} to {self.ip}:{self.port} - {e}")
            import traceback
            traceback.print_exc()
