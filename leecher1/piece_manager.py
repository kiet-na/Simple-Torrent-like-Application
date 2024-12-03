# piece_manager.py

import hashlib
import os
import threading

class PieceManager:
    def __init__(self, metainfo, download_directory, verbose=False):
        self.metainfo = metainfo
        self.download_directory = download_directory
        self.verbose = verbose
        self.piece_length = self.metainfo[b'info'][b'piece length']
        self.total_length = self.calculate_total_length()
        self.total_pieces = (self.total_length + self.piece_length - 1) // self.piece_length
        self.pieces = {}  # Verified pieces by index
        self.pieces_data = {}  # Assembling piece data
        self.blocks_received = {}  # Received blocks for each piece
        self.missing_pieces = set(range(self.total_pieces))
        self.downloaded = 0
        self.uploaded = 0
        self.file_mappings = self.create_file_mappings()
        self.piece_availability = [0] * self.total_pieces
        self.lock = threading.Lock()
        self.peer_piece_map = {}  # {peer_id: set(piece_indices)}
        # Initialize piece hashes
        pieces = self.metainfo[b'info'][b'pieces']
        self.piece_hashes = [pieces[i:i + 20] for i in range(0, len(pieces), 20)]

    def calculate_total_length(self):
        if b'length' in self.metainfo[b'info']:
            return self.metainfo[b'info'][b'length']
        elif b'files' in self.metainfo[b'info']:
            return sum(file[b'length'] for file in self.metainfo[b'info'][b'files'])
        else:
            raise ValueError("Invalid metainfo: missing 'length' or 'files' key")

    def create_file_mappings(self):
        mappings = []
        offset = 0
        root_directory = self.metainfo[b'info'][b'name'].decode('utf-8')
        if b'files' in self.metainfo[b'info']:
            for file_info in self.metainfo[b'info'][b'files']:
                path = os.path.join(root_directory, *[p.decode() for p in file_info[b'path']])
                mappings.append({
                    'path': path,
                    'length': file_info[b'length'],
                    'offset': offset,
                })
                offset += file_info[b'length']
        else:
            length = self.metainfo[b'info'][b'length']
            name = self.metainfo[b'info'][b'name'].decode()
            path = os.path.join(self.download_directory, name)
            mappings.append({
                'path': path,
                'length': length,
                'offset': 0,
            })
        return mappings

    def load_pieces_from_file(self):
        """
        Load existing pieces from local files (used by the seeder).
        """
        with self.lock:
            for mapping in self.file_mappings:
                file_path = os.path.join(self.download_directory, mapping['path'])
                if not os.path.exists(file_path):
                    if self.verbose:
                        print(f"File {file_path} does not exist.")
                    continue
                with open(file_path, 'rb') as f:
                    file_offset = mapping['offset']
                    remaining = mapping['length']
                    while remaining > 0:
                        piece_index = file_offset // self.piece_length
                        piece_offset = file_offset % self.piece_length
                        read_length = min(remaining, self.get_piece_length(piece_index) - piece_offset)
                        data = f.read(read_length)
                        if not data:
                            break
                        if piece_index not in self.pieces_data:
                            self.pieces_data[piece_index] = bytearray(self.get_piece_length(piece_index))
                        self.pieces_data[piece_index][piece_offset:piece_offset + len(data)] = data
                        file_offset += len(data)
                        remaining -= len(data)
                    if self.verbose:
                        print(f"Loaded data from {file_path}")

            # Verify and store the pieces
            for index, data in self.pieces_data.items():
                expected_hash = self.piece_hashes[index]
                actual_hash = hashlib.sha1(data).digest()
                if actual_hash == expected_hash:
                    self.pieces[index] = data
                    self.missing_pieces.discard(index)
                    if self.verbose:
                        print(f"Piece {index} loaded and verified.")
                else:
                    if self.verbose:
                        print(f"Piece {index} failed verification.")
            self.pieces_data.clear()

    def add_block(self, index, begin, block):
        piece_length = self.get_piece_length(index)
        with self.lock:
            if index not in self.pieces_data:
                self.pieces_data[index] = bytearray(piece_length)
                self.blocks_received[index] = set()
            self.pieces_data[index][begin:begin + len(block)] = block
            self.blocks_received[index].add(begin)
            if self.is_piece_fully_received(index):
                if self.verify_piece(index):
                    self.pieces[index] = self.pieces_data.pop(index)
                    self.blocks_received.pop(index)
                    self.missing_pieces.discard(index)
                    self.downloaded += piece_length
                    if self.verbose:
                        print(f"Piece {index} verified and stored. Total downloaded: {self.downloaded} bytes.")
                else:
                    del self.pieces_data[index]
                    del self.blocks_received[index]
                    if self.verbose:
                        print(f"Piece {index} failed verification and was discarded.")

    def is_piece_fully_received(self, index):
        piece_length = self.get_piece_length(index)
        block_size = 2 ** 14  # 16KB blocks
        expected_blocks = (piece_length + block_size - 1) // block_size
        received_blocks = len(self.blocks_received.get(index, set()))
        return received_blocks == expected_blocks

    def verify_piece(self, index):
        piece_data = self.pieces_data.get(index)
        if piece_data is None:
            return False
        expected_hash = self.piece_hashes[index]
        actual_hash = hashlib.sha1(piece_data).digest()
        return actual_hash == expected_hash

    def get_piece_length(self, index):
        if index == self.total_pieces - 1:
            return self.total_length - index * self.piece_length
        else:
            return self.piece_length

    def has_piece(self, index):
        return index in self.pieces

    def is_complete(self):
        return len(self.pieces) == self.total_pieces

    def reconstruct_files(self):
        for mapping in self.file_mappings:
            file_path = os.path.join(self.download_directory, mapping['path'])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                file_offset = mapping['offset']
                remaining = mapping['length']
                while remaining > 0:
                    piece_index = file_offset // self.piece_length
                    piece_offset = file_offset % self.piece_length
                    piece_data = self.pieces.get(piece_index)
                    if piece_data is None:
                        print(f"Missing piece {piece_index}, cannot reconstruct file.")
                        return
                    read_length = min(remaining, self.get_piece_length(piece_index) - piece_offset)
                    f.write(piece_data[piece_offset:piece_offset + read_length])
                    file_offset += read_length
                    remaining -= read_length
        print(f"Files reconstructed at {self.download_directory}")

    def has_piece_in_bitfield(self, bitfield, index):
        byte_index = index // 8
        bit_index = index % 8
        if byte_index >= len(bitfield):
            return False
        return (bitfield[byte_index] >> (7 - bit_index)) & 1

    def get_rarest_pieces(self):
        missing_pieces = list(self.missing_pieces)
        missing_pieces.sort(key=lambda index: self.piece_availability[index])
        if self.verbose:
            print(f"Rarest pieces sorted: {missing_pieces}")
        return missing_pieces

    def get_bitfield(self):
        bitfield_length = (self.total_pieces + 7) // 8
        bitfield = bytearray(bitfield_length)
        for index in self.pieces.keys():
            byte_index = index // 8
            bit_index = index % 8
            bitfield[byte_index] |= 1 << (7 - bit_index)
        return bytes(bitfield)
    def get_piece(self, index):
        with self.lock:
            return self.pieces.get(index)

    def update_piece_availability(self, peer_bitfield, peer_id):
        if peer_id not in self.peer_piece_map:
            self.peer_piece_map[peer_id] = set()
        for index in range(len(peer_bitfield) * 8):
            if self.has_piece_in_bitfield(peer_bitfield, index):
                if index not in self.peer_piece_map[peer_id]:
                    self.peer_piece_map[peer_id].add(index)
                    self.piece_availability[index] += 1
                    if self.verbose:
                        print(f"Piece {index} availability incremented to {self.piece_availability[index]}")
                else:
                    if self.verbose:
                        print(f"Already accounted for piece {index} from peer {peer_id}.")

    def update_piece_availability_for_piece(self, index, peer_id):
        if peer_id not in self.peer_piece_map:
            self.peer_piece_map[peer_id] = set()
        if index not in self.peer_piece_map[peer_id]:
            self.peer_piece_map[peer_id].add(index)
            self.piece_availability[index] += 1
            if self.verbose:
                print(f"Piece {index} availability incremented to {self.piece_availability[index]}")
        else:
            if self.verbose:
                print(f"Already accounted for piece {index} from peer {peer_id}.")

    def remove_peer(self, peer_id):
        if peer_id in self.peer_piece_map:
            for index in self.peer_piece_map[peer_id]:
                self.piece_availability[index] -= 1
                if self.verbose:
                    print(f"Piece {index} availability decremented to {self.piece_availability[index]}")
            del self.peer_piece_map[peer_id]