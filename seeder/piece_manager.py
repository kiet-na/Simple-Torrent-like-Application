# piece_manager.py

import hashlib
import os
import threading

class PieceManager:
    def __init__(self, metainfo, download_directory):
        self.metainfo = metainfo
        self.download_directory = download_directory
        self.piece_length = self.metainfo[b'info'][b'piece length']
        self.total_length = self.calculate_total_length()
        self.total_pieces = (self.total_length + self.piece_length - 1) // self.piece_length
        self.pieces = {}  # Dictionary to store verified pieces by index
        self.pieces_data = {}  # Temporary storage for assembling piece data
        self.missing_pieces = set(range(self.total_pieces))
        self.downloaded = 0
        self.uploaded = 0

        # Prepare file mappings
        self.file_mappings = self.create_file_mappings()

        # Initialize piece availability for rarest-first
        self.piece_availability = [0] * self.total_pieces

        # Initialize requested pieces tracking
        self.requested_pieces = set()

        # Lock for thread safety
        self.lock = threading.Lock()

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
        if b'files' in self.metainfo[b'info']:
            files = self.metainfo[b'info'][b'files']
            # Generate a list of files with their paths as strings for sorting
            files_with_paths = []
            for file_info in files:
                path_components = [component.decode('utf-8') for component in file_info[b'path']]
                path_string = os.sep.join(path_components)
                files_with_paths.append((path_string, file_info))
            # Sort the files based on the path string
            files_with_paths.sort(key=lambda x: x[0])

            # Print the sorted file paths
            print("Files in piece_manager.py:")
            for path_string, _ in files_with_paths:
                print(path_string)

            # Now process the files in sorted order
            for path_string, file_info in files_with_paths:
                length = file_info[b'length']
                path_components = path_string.split(os.sep)
                mappings.append({
                    'path': path_components,
                    'length': length,
                    'offset': offset
                })
                offset += length
        else:
            # Single file
            length = self.metainfo[b'info'][b'length']
            name = self.metainfo[b'info'][b'name'].decode('utf-8')
            mappings.append({
                'path': [name],
                'length': length,
                'offset': 0
            })
        return mappings

    def add_piece(self, index, data):
        if index in self.pieces:
            return  # Already have this piece
        expected_hash = self.get_piece_hash(index)
        actual_hash = hashlib.sha1(data).digest()
        if actual_hash == expected_hash:
            self.pieces[index] = data
            self.missing_pieces.discard(index)
            self.requested_pieces.discard(index)
            self.downloaded += len(data)
            print(f"Piece {index} verified and added. Total downloaded: {self.downloaded} bytes.")
        else:
            print(f"Piece {index} failed hash check.")
            self.requested_pieces.discard(index)  # Allow re-requesting

    def get_piece(self, index):
        return self.pieces.get(index)

    def get_piece_hash(self, index):
        start = index * 20  # Each SHA-1 hash is 20 bytes
        end = start + 20
        return self.metainfo[b'info'][b'pieces'][start:end]

    def get_piece_length(self, index):
        if index == self.total_pieces - 1:
            return self.total_length - index * self.piece_length
        else:
            return self.piece_length

    def next_missing_piece(self):
        if self.missing_pieces:
            # Return the rarest piece available
            missing_pieces = list(self.missing_pieces)
            missing_pieces.sort(key=lambda index: self.piece_availability[index])
            for piece in missing_pieces:
                if piece not in self.requested_pieces:
                    return piece
        return None

    def is_complete(self):
        return len(self.missing_pieces) == 0

    def reconstruct_files(self, base_path):
        for file_info in self.file_mappings:
            file_path = os.path.join(base_path, *file_info['path'])
            file_dir = os.path.dirname(file_path)
            if not os.path.exists(file_dir):
                os.makedirs(file_dir)

            with open(file_path, 'wb') as outfile:
                file_offset = file_info['offset']
                remaining = file_info['length']
                while remaining > 0:
                    piece_index = file_offset // self.piece_length
                    piece_offset = file_offset % self.piece_length
                    piece_data = self.pieces.get(piece_index)
                    if piece_data is None:
                        print(f"Missing piece {piece_index}, cannot reconstruct file.")
                        return
                    read_length = min(remaining, self.piece_length - piece_offset)
                    outfile.write(piece_data[piece_offset:piece_offset + read_length])
                    file_offset += read_length
                    remaining -= read_length
        print(f"Files reconstructed at {base_path}")

    def load_pieces_from_file(self, base_path):
        total_offset = 0
        total_loaded_length = 0
        for file_info in self.file_mappings:
            file_path = os.path.join(base_path, *file_info['path'])
            if not os.path.exists(file_path):
                print(f"File {file_path} does not exist.")
                continue

            file_length = file_info['length']
            with open(file_path, 'rb') as f:
                remaining = file_length
                while remaining > 0:
                    piece_index = total_offset // self.piece_length
                    piece_offset = total_offset % self.piece_length
                    read_length = min(self.get_piece_length(piece_index) - piece_offset, remaining)
                    data = f.read(read_length)
                    if not data:
                        break

                    if piece_index not in self.pieces_data:
                        piece_length = self.get_piece_length(piece_index)
                        self.pieces_data[piece_index] = bytearray(piece_length)
                    self.pieces_data[piece_index][piece_offset:piece_offset + len(data)] = data

                    total_offset += len(data)
                    total_loaded_length += len(data)
                    remaining -= len(data)

        print(f"Total loaded data length: {total_loaded_length}")
        print(f"Expected total length: {self.total_length}")
        # Proceed with verifying pieces...

        # After reading all files, verify and store the pieces
        for index, piece_data in self.pieces_data.items():
            expected_hash = self.get_piece_hash(index)
            actual_hash = hashlib.sha1(piece_data).digest()
            if actual_hash == expected_hash:
                self.pieces[index] = bytes(piece_data)
                self.missing_pieces.discard(index)
                print(f"Piece {index} loaded and verified.")
            else:
                print(f"Piece {index} failed hash check during loading.")
        for index, piece_data in self.pieces_data.items():
            expected_length = self.get_piece_length(index)
            actual_length = len(piece_data)
            print(f"Piece {index} expected length: {expected_length}, actual length: {actual_length}")

    def update_piece_availability(self, peer_bitfield):
        for index in range(self.total_pieces):
            if self.has_piece_in_bitfield(peer_bitfield, index):
                self.piece_availability[index] += 1
                print(f"Piece {index} availability incremented to {self.piece_availability[index]}")

    def has_piece_in_bitfield(self, bitfield, index):
        byte_index = index // 8
        bit_index = index % 8
        if byte_index >= len(bitfield):
            return False
        return (bitfield[byte_index] >> (7 - bit_index)) & 1

    def update_piece_availability_for_piece(self, index):
        self.piece_availability[index] += 1
        print(f"Piece {index} availability incremented to {self.piece_availability[index]}")

    def has_piece(self, index):
        return index in self.pieces

    def get_rarest_pieces(self):
        # Return missing pieces sorted by availability
        missing_pieces = list(self.missing_pieces)
        missing_pieces.sort(key=lambda index: self.piece_availability[index])
        return missing_pieces

    def get_bitfield(self):
        bitfield_length = (self.total_pieces + 7) // 8
        bitfield = bytearray(bitfield_length)
        for index in self.pieces.keys():
            byte_index = index // 8
            bit_index = index % 8
            bitfield[byte_index] |= 1 << (7 - bit_index)
        return bytes(bitfield)


