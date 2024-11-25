# node_client.py

import threading
import socket
import requests
import time
import os
import random
import string
from piece_manager import PieceManager
from peer_connection import PeerConnection
import bencodepy
import hashlib
import sys
from queue import Queue

class NodeClient:
    def __init__(self, tracker_url, listening_port, role):
        self.tracker_url = tracker_url
        self.listening_port = listening_port
        self.role = role  # 'seeder' or 'leecher'
        self.running = True
        self.peers = []
        self.peer_id = self.generate_peer_id()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.metainfo = None
        self.info_hash = None
        self.piece_manager = None
        self.connected_peers = []
        self.connected_peer_addresses = set()  # Track connected peer addresses as (ip, port) tuples
        self.request_queue = Queue()
        self.piece_hashes = []

    def generate_peer_id(self):
        peer_id = '-STA0001-' + ''.join(random.choices(string.digits, k=11))
        assert len(peer_id) == 20, f"peer_id length is {len(peer_id)}, expected 20."
        return peer_id

    def start(self):
        if not self.load_torrent('files/example.torrent'):
            print("Failed to load torrent file. Exiting.")
            return

        # Start listening for peers (both seeders and leechers)
        threading.Thread(target=self.listen_for_peers, daemon=True).start()

        # Announce to tracker
        self.announce_to_tracker(event='started')

        # Start main loop
        self.main_loop()

    def load_torrent(self, torrent_path):
        # Get the directory of the main script (e.g., run_node.py or run_node2.py)
        node_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))

        # Construct the full path to the torrent file
        torrent_full_path = os.path.join(node_dir, torrent_path)
        if not os.path.exists(torrent_full_path):
            print(f"Torrent file {torrent_full_path} does not exist.")
            return False

        with open(torrent_full_path, 'rb') as tf:
            metainfo = bencodepy.decode(tf.read())

        self.metainfo = metainfo  # Keys are bytes

        # Calculate info_hash and extract piece hashes
        info = self.metainfo[b'info']
        encoded_info = bencodepy.encode(info)
        self.info_hash = hashlib.sha1(encoded_info).digest()  # Use raw bytes
        pieces = self.metainfo[b'info'][b'pieces']
        self.piece_hashes = [pieces[i:i + 20] for i in range(0, len(pieces), 20)]

        self.piece_manager = PieceManager(self.metainfo)
        self.piece_manager.piece_hashes = self.piece_hashes

        # Construct the file path for the shared file/directory
        file_name = self.metainfo[b'info'][b'name'].decode('utf-8')
        file_path = os.path.join(node_dir, file_name)

        if os.path.exists(file_path):
            print(f"{self.role.capitalize()}: File {file_path} exists locally. Loading pieces...")
            self.piece_manager.load_pieces_from_file(file_path)
        else:
            if self.role == 'seeder':
                print(f"Seeder: File {file_path} does not exist locally. Cannot seed.")
            else:
                print(f"Leecher: File {file_path} does not exist locally. Starting download...")
        return True

    def listen_for_peers(self):
        self.server_socket.bind(('', self.listening_port))
        self.server_socket.listen(5)
        print(f"Listening for peers on port {self.listening_port}...")
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Accepted connection from {addr}")
                peer_conn = PeerConnection.from_incoming(client_socket, self.piece_manager, self.peer_id, self.info_hash, self)
                peer_conn.start()
                self.connected_peers.append(peer_conn)
                # Note: Peer ID is not known yet; will be updated after handshake
            except Exception as e:
                print(f"Error accepting connections: {e}")

    def announce_to_tracker(self, event):
        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id,
            'port': self.listening_port,
            'uploaded': self.piece_manager.uploaded,
            'downloaded': self.piece_manager.downloaded,
            'left': self.piece_manager.total_length - self.piece_manager.downloaded,
            'event': event
        }
        try:
            response = requests.get(f"{self.tracker_url}/announce", params=params)
            if response.status_code == 200:
                data = response.json()
                self.peers = data.get('peers', [])
                print(f"Received {len(self.peers)} peers from tracker.")
                print(f"{self.role.capitalize()} received peers: {self.peers}")
            else:
                print(f"Tracker announce failed with status code {response.status_code}.")
        except Exception as e:
            print(f"Error announcing to tracker: {e}")

    def main_loop(self):
        if self.role == 'seeder':
            print("Seeder is ready to upload to peers.")
            while self.running:
                time.sleep(10)  # Keep the seeder running
        else:
            while self.running and not self.piece_manager.is_complete():
                self.connect_to_peers()
                time.sleep(10)
            if self.piece_manager.is_complete():
                print("Download complete.")
                # Reconstruct the files
                node_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
                download_dir = os.path.join(node_dir, self.metainfo[b'info'][b'name'].decode('utf-8'))
                self.piece_manager.reconstruct_files(download_dir)
                self.announce_to_tracker(event='completed')
                self.display_statistics()

                # Switch role to 'seeder'
                self.role = 'seeder'
                print("Now acting as seeder. Ready to upload to peers.")

                # Continue running as seeder
                while self.running:
                    time.sleep(10)  # Keep the seeder running

    def connect_to_peers(self):
        for peer_info in self.peers:
            ip = peer_info.get('ip')
            port = int(peer_info.get('port'))

            peer_address = (ip, port)
            if peer_address in self.connected_peer_addresses:
                print(f"Already connected to peer at {ip}:{port}")
                continue

            print(f"Connecting to peer {ip}:{port}")
            peer_conn = PeerConnection(ip, port, self.piece_manager, self.peer_id, self.info_hash, self)
            peer_conn.start()
            self.connected_peers.append(peer_conn)
            self.connected_peer_addresses.add(peer_address)

    def display_statistics(self):
        print(f"Downloaded: {self.piece_manager.downloaded} bytes")
        print(f"Uploaded: {self.piece_manager.uploaded} bytes")
