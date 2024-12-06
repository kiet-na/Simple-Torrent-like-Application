import threading
import socket
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
import urllib.parse
import requests

class NodeClient:
    def __init__(self, torrent_file, listen_port, download_directory, max_download_speed=0, max_upload_speed=0, verbose=False, role='leecher'):
        self.torrent_file = torrent_file
        self.listen_port = listen_port
        self.download_directory = download_directory
        self.max_download_speed = max_download_speed  # Bytes per second (not actively enforced in this code)
        self.max_upload_speed = max_upload_speed      # Bytes per second (not actively enforced in this code)
        self.verbose = verbose
        self.role = role  # 'seeder' or 'leecher'
        self.request_timestamps = {}
        self.request_timeout = 30  # seconds
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
        self.requested_pieces = set()
        # Lock for thread safety when modifying connected_peers and connected_peer_addresses
        self.lock = threading.Lock()

        # Tracker URL (Assuming it's in the .torrent file)
        self.tracker_url = None

        self.has_announced_started = False  # To track if 'started' event has been sent

        # For improved speed calculation and display
        self.download_history = []
        self.upload_history = []

    def generate_peer_id(self):
        # Ensure peer_id is exactly 20 bytes
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

        # Start main loop threads
        threading.Thread(target=self.handle_piece_download_timeout, daemon=True).start()
        self.main_loop()

    def load_torrent(self, torrent_path):
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

        self.piece_manager = PieceManager(self.metainfo, self.download_directory, verbose=self.verbose)

        # If role is 'seeder', load existing pieces
        if self.role == 'seeder':
            if self.verbose:
                print(f"Seeder: Loading existing pieces from {self.download_directory}")
            self.piece_manager.load_pieces_from_file()
        else:
            if self.verbose:
                print(f"Leecher: Starting download to {self.download_directory}")

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
                if not self.running:
                    break
                if self.verbose:
                    print(f"Accepted connection from {addr}")
                peer_conn = PeerConnection.from_incoming(client_socket, self.piece_manager, self.peer_id, self.info_hash, self, verbose=self.verbose)
                peer_conn.start()
                with self.lock:
                    self.connected_peers.append(peer_conn)
            except Exception as e:
                if self.verbose:
                    print(f"Error accepting connections: {e}")

    def announce_to_tracker(self, event=None):
        if not self.tracker_url:
            return
        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id.encode('utf-8'),
            'port': self.listen_port,
            'uploaded': self.piece_manager.uploaded,
            'downloaded': self.piece_manager.downloaded,
            'left': self.piece_manager.total_length - self.piece_manager.downloaded,
        }
        if event:
            params['event'] = event

        # Properly URL-encode the parameters
        encoded_params = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        announce_url = f"{self.tracker_url}?{encoded_params}"

        try:
            response = requests.get(announce_url)
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
        # Start initial tracker announce
        if not self.has_announced_started:
            self.announce_to_tracker(event='started')
            self.has_announced_started = True

        # Start threads
        threading.Thread(target=self.populate_request_queue, daemon=True).start()
        threading.Thread(target=self.connect_to_peers_loop, daemon=True).start()
        threading.Thread(target=self.display_statistics, daemon=True).start()
        threading.Thread(target=self.periodic_tracker_announce, daemon=True).start()

        while self.running:
            if self.role == 'leecher' and self.piece_manager.is_complete():
                print("\nDownload complete.")
                # Reconstruct the files
                self.piece_manager.reconstruct_files()
                self.announce_to_tracker(event='completed')
                print(f"Downloaded: {self.piece_manager.downloaded} bytes")
                print(f"Uploaded: {self.piece_manager.uploaded} bytes")
                print("Now acting as seeder. Ready to upload to peers.")
                self.role = 'seeder'
            time.sleep(1)

    def periodic_tracker_announce(self):
        while self.running:
            time.sleep(1800)  # Announce every 30 minutes
            self.announce_to_tracker()

    def populate_request_queue(self):
        while self.running:
            if self.role == 'leecher':
                with self.piece_manager.lock:
                    rarest_pieces = self.piece_manager.get_rarest_pieces()
                    for index in rarest_pieces:
                        if index not in self.piece_manager.pieces:
                            if index not in self.requested_pieces:
                                priority = self.piece_manager.piece_availability[index]
                                self.request_queue.put((priority, index))
                                if self.verbose:
                                    print(f"Added piece {index} with priority {priority} to the request queue.")
            time.sleep(5)

    def connect_to_peers_loop(self):
        while self.running:
            self.connect_to_peers()
            time.sleep(30)  # Attempt to connect every 30 seconds

    def connect_to_peers(self):
        self.announce_to_tracker()
        for peer_info in self.peers:
            if not self.running:
                break
            ip = peer_info.get('ip')
            port = int(peer_info.get('port'))

            peer_address = (ip, port)
            with self.lock:
                if peer_address in self.connected_peer_addresses or peer_address == ('127.0.0.1', self.listen_port):
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
                current_time = time.time()
                if (piece_index in self.requested_pieces and
                        current_time - self.request_timestamps.get(piece_index, 0) < self.request_timeout):
                    # Re-add the piece to the queue for retry
                    self.request_queue.put((priority, piece_index))
                    return None
                self.requested_pieces.add(piece_index)
                self.request_timestamps[piece_index] = current_time
                if self.verbose:
                    print(f"Requesting piece {piece_index} with priority {priority}.")
                return piece_index
        except Empty:
            if self.verbose:
                print("Request queue is empty. No pieces to request.")
            return None

    def handle_piece_download_timeout(self):
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            current_time = time.time()
            with self.request_lock:
                for piece_index in list(self.requested_pieces):
                    if current_time - self.request_timestamps.get(piece_index, 0) > self.request_timeout:
                        if self.verbose:
                            print(f"Timeout for piece {piece_index}. Re-adding to request queue.")
                        self.requested_pieces.discard(piece_index)
                        self.request_timestamps.pop(piece_index, None)
                        priority = self.piece_manager.piece_availability[piece_index]
                        self.request_queue.put((priority, piece_index))

    def notify_piece_downloaded(self, piece_index):
        with self.request_lock:
            self.requested_pieces.discard(piece_index)
            self.request_timestamps.pop(piece_index, None)
        if self.verbose:
            print(f"Piece {piece_index} downloaded and verified.")

    def send_have_to_all(self, piece_index):
        with self.lock:
            for peer_conn in self.connected_peers:
                peer_conn.send_have(piece_index)

    def display_statistics(self):
        start_time = time.time()
        previous_time = start_time
        previous_downloaded = self.piece_manager.downloaded
        previous_uploaded = self.piece_manager.uploaded

        while self.running:
            time.sleep(1)
            current_time = time.time()
            interval = current_time - previous_time
            elapsed = current_time - start_time
            previous_time = current_time

            downloaded = self.piece_manager.downloaded
            uploaded = self.piece_manager.uploaded
            # Instantaneous speeds
            instantaneous_download_speed = (downloaded - previous_downloaded) / interval if interval > 0 else 0
            instantaneous_upload_speed = (uploaded - previous_uploaded) / interval if interval > 0 else 0

            # Cumulative average speeds
            avg_download_speed = downloaded / elapsed if elapsed > 0 else 0
            avg_upload_speed = uploaded / elapsed if elapsed > 0 else 0

            previous_downloaded = downloaded
            previous_uploaded = uploaded

            progress = (
                                   len(self.piece_manager.pieces) / self.piece_manager.total_pieces) * 100 if self.piece_manager.total_pieces > 0 else 0


    def stop(self):
        # Graceful shutdown
        self.running = False
        # Announce 'stopped' event to the tracker
        self.announce_to_tracker(event='stopped')

        # Close peer connections and clear peers
        with self.lock:
            # Close all peer connections gracefully
            for peer_conn in self.connected_peers:
                peer_conn.running = False
                try:
                    peer_conn.socket.close()
                except Exception:
                    pass
            self.connected_peers.clear()
            self.connected_peer_addresses.clear()

        # Clear out the peer list since we are no longer participating
        self.peers.clear()

        # Close the server socket if it's open
        try:
            self.server_socket.close()
        except Exception:
            pass

        print("\nClient stopped and tracker notified. Peer list and connections cleared.")

