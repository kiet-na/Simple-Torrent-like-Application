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
from queue import PriorityQueue, Empty

class NodeClient:
    def __init__(self, torrent_file, listen_port, download_directory, max_download_speed=0, max_upload_speed=0, verbose=False, role='leecher'):
        self.torrent_file = torrent_file
        self.listen_port = listen_port
        self.download_directory = download_directory
        self.max_download_speed = max_download_speed  # Bytes per second (Not implemented)
        self.max_upload_speed = max_upload_speed      # Bytes per second (Not implemented)
        self.verbose = verbose
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
        self.request_queue = PriorityQueue()  # PriorityQueue to manage Rarest First
        self.request_lock = threading.Lock()  # To synchronize access to the request queue
        self.piece_hashes = []

        # Lock for thread safety when modifying connected_peers and connected_peer_addresses
        self.lock = threading.Lock()

    def generate_peer_id(self):
        # Ensure peer_id is exactly 20 characters
        peer_id = '-PC0001-' + ''.join(random.choices(string.digits, k=12))
        if len(peer_id) != 20:
            raise ValueError(f"peer_id length is {len(peer_id)}, expected 20.")
        return peer_id

    def start(self):
        if not self.load_torrent(self.torrent_file):
            print("Failed to load torrent file. Exiting.")
            return

        # Start listening for peers (both seeders and leechers)
        threading.Thread(target=self.listen_for_peers, daemon=True).start()

        # Announce to tracker
        self.announce_to_tracker(event='started')

        # Start main loop
        self.main_loop()

    def load_torrent(self, torrent_path):
        # Adjusted to use the provided torrent file path
        if not os.path.exists(torrent_path):
            print(f"Torrent file {torrent_path} does not exist.")
            return False

        with open(torrent_path, 'rb') as tf:
            try:
                metainfo = bencodepy.decode(tf.read())
            except bencodepy.exceptions.DecodingError as e:
                print(f"DecodingError while parsing torrent file: {e}")
                return False

        self.metainfo = metainfo  # Keys are bytes

        # Extract tracker URL
        self.tracker_url = self.metainfo.get(b'announce').decode('utf-8')

        # Calculate info_hash and extract piece hashes
        info = self.metainfo[b'info']
        encoded_info = bencodepy.encode(info)
        self.info_hash = hashlib.sha1(encoded_info).digest()  # Use raw bytes
        pieces = self.metainfo[b'info'][b'pieces']
        self.piece_hashes = [pieces[i:i + 20] for i in range(0, len(pieces), 20)]

        self.piece_manager = PieceManager(self.metainfo, self.download_directory, verbose=self.verbose)

        # No need to assign piece_hashes separately since PieceManager retrieves them from metainfo

        # Construct the file path for the shared file/directory
        file_name = self.metainfo[b'info'][b'name'].decode('utf-8')
        file_path = os.path.join(self.download_directory, file_name)

        if os.path.exists(self.download_directory):
            print(f"{self.role.capitalize()}: Directory {self.download_directory} exists locally. Loading pieces...")
            self.piece_manager.load_pieces_from_file(self.download_directory)
        else:
            if self.role == 'seeder':
                print(f"Seeder: Directory {self.download_directory} does not exist locally. Cannot seed.")
                return False
            else:
                print(f"Leecher: Directory {self.download_directory} does not exist locally. Starting download...")
        return True

    def listen_for_peers(self):
        try:
            self.server_socket.bind(('', self.listen_port))
            self.server_socket.listen(5)
            if self.verbose:
                print(f"Listening for peers on port {self.listen_port}...")
        except Exception as e:
            print(f"Failed to bind to port {self.listen_port}: {e}")
            return

        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                if self.verbose:
                    print(f"Accepted connection from {addr}")
                peer_conn = PeerConnection.from_incoming(client_socket, self.piece_manager, self.peer_id, self.info_hash, self, verbose=self.verbose)
                peer_conn.start()
                with self.lock:
                    self.connected_peers.append(peer_conn)
                # Note: Peer ID is not known yet; will be updated after handshake
            except Exception as e:
                if self.verbose:
                    print(f"Error accepting connections: {e}")

    def announce_to_tracker(self, event):
        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id.encode('utf-8'),
            'port': self.listen_port,
            'uploaded': self.piece_manager.uploaded,
            'downloaded': self.piece_manager.downloaded,
            'left': self.piece_manager.total_length - self.piece_manager.downloaded,
            'event': event
        }
        try:
            response = requests.get(self.tracker_url, params=params)
            if response.status_code == 200:
                data = bencodepy.decode(response.content)
                peers = data.get(b'peers')
                if isinstance(peers, list):
                    # Dictionary model
                    self.peers = [{'ip': peer[b'ip'].decode('utf-8'), 'port': peer[b'port']} for peer in peers]
                else:
                    # Binary model (compact representation)
                    self.peers = self.parse_compact_peers(peers)
                if self.verbose:
                    print(f"Received {len(self.peers)} peers from tracker.")
                    print(f"{self.role.capitalize()} received peers: {self.peers}")
            else:
                print(f"Tracker announce failed with status code {response.status_code}.")
        except Exception as e:
            print(f"Error announcing to tracker: {e}")

    def parse_compact_peers(self, peers_binary):
        peers = []
        for i in range(0, len(peers_binary), 6):
            ip = '.'.join(str(b) for b in peers_binary[i:i+4])
            port = int.from_bytes(peers_binary[i+4:i+6], 'big')
            peers.append({'ip': ip, 'port': port})
        return peers

    def main_loop(self):
        if self.role == 'seeder':
            print("Seeder is ready to upload to peers.")
            while self.running:
                time.sleep(10)  # Keep the seeder running
        else:
            # Initialize the request queue with rarest pieces first
            threading.Thread(target=self.populate_request_queue, daemon=True).start()

            # Start connecting to peers
            threading.Thread(target=self.connect_to_peers_loop, daemon=True).start()

            # Start displaying statistics
            threading.Thread(target=self.display_statistics, daemon=True).start()

            # Keep the main thread alive
            while self.running and not self.piece_manager.is_complete():
                time.sleep(1)
            if self.piece_manager.is_complete():
                print("\nDownload complete.")
                # Reconstruct the files
                self.piece_manager.reconstruct_files(self.download_directory)
                self.announce_to_tracker(event='completed')
                print(f"Downloaded: {self.piece_manager.downloaded} bytes")
                print(f"Uploaded: {self.piece_manager.uploaded} bytes")
                print("Now acting as seeder. Ready to upload to peers.")
                self.role = 'seeder'
                # Continue running as seeder
                while self.running:
                    time.sleep(10)  # Keep the seeder running

    def populate_request_queue(self):
        while not self.piece_manager.is_complete() and self.running:
            with self.piece_manager.lock:
                rarest_pieces = self.piece_manager.get_rarest_pieces()
                for index in rarest_pieces:
                    if index not in self.piece_manager.requested_pieces and index not in self.piece_manager.pieces:
                        priority = self.piece_manager.piece_availability[index]
                        self.request_queue.put((priority, index))
                        if self.verbose:
                            print(f"Added piece {index} with priority {priority} to the request queue.")
            time.sleep(5)

    def connect_to_peers_loop(self):
        while self.running and not self.piece_manager.is_complete():
            self.connect_to_peers()
            time.sleep(30)  # Attempt to connect every 30 seconds

    def connect_to_peers(self):
        for peer_info in self.peers:
            ip = peer_info.get('ip')
            port = int(peer_info.get('port'))

            peer_address = (ip, port)
            with self.lock:
                if peer_address in self.connected_peer_addresses:
                    if self.verbose:
                        print(f"Already connected to peer at {ip}:{port}")
                    continue

            if self.verbose:
                print(f"Connecting to peer {ip}:{port}")
            try:
                peer_conn = PeerConnection(ip, port, self.piece_manager, self.peer_id, self.info_hash, self, verbose=self.verbose)
                peer_conn.start()
                with self.lock:
                    self.connected_peers.append(peer_conn)
                    self.connected_peer_addresses.add(peer_address)
                if self.verbose:
                    print(f"Connected to peer {ip}:{port}")
            except Exception as e:
                if self.verbose:
                    print(f"Failed to connect to peer {ip}:{port} - {e}")

    def request_piece_from_rarest(self):
        try:
            priority, piece_index = self.request_queue.get(timeout=10)
            with self.request_lock:
                if piece_index in self.piece_manager.requested_pieces or piece_index in self.piece_manager.pieces:
                    if self.verbose:
                        print(f"Piece {piece_index} already requested or downloaded. Skipping.")
                    return None  # Already requested or downloaded
                self.piece_manager.requested_pieces.add(piece_index)
                if self.verbose:
                    print(f"Requesting piece {piece_index} with priority {priority}.")
                return piece_index
        except Empty:
            if self.verbose:
                print("Request queue is empty. No pieces to request.")
            return None  # No pieces available to request

    def notify_piece_downloaded(self, piece_index):
        with self.request_lock:
            # Update piece availability since a new peer now has this piece
            self.piece_manager.piece_availability[piece_index] += 1
            if self.verbose:
                print(f"Piece {piece_index} is now available with availability {self.piece_manager.piece_availability[piece_index]}.")
            # Re-populate the queue as piece availability might have changed
            # This might be redundant if 'populate_request_queue' is running continuously

    def display_statistics(self):
        previous_downloaded = 0
        previous_uploaded = 0
        while not self.piece_manager.is_complete() and self.running:
            time.sleep(1)
            downloaded = self.piece_manager.downloaded
            uploaded = self.piece_manager.uploaded
            download_speed = downloaded - previous_downloaded  # Bytes per second
            upload_speed = uploaded - previous_uploaded
            previous_downloaded = downloaded
            previous_uploaded = uploaded
            progress = (len(self.piece_manager.pieces) / self.piece_manager.total_pieces) * 100
            print(f"\rProgress: {progress:.2f}% | Downloaded: {downloaded} bytes ({download_speed} B/s) | Uploaded: {uploaded} bytes ({upload_speed} B/s)", end='')
        print("\nDownload statistics display terminated.")
