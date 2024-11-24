# piece_manager.py

import hashlib
import os

class PieceManager:
    def __init__(self, metainfo):
        self.metainfo = metainfo
        self.piece_length = self.metainfo[b'info'][b'piece length']
        self.total_length = self.metainfo[b'info'][b'length']
        self.total_pieces = (self.total_length + self.piece_length - 1) // self.piece_length
        self.pieces = {}  # Dictionary to store pieces by index
        self.missing_pieces = set(range(self.total_pieces))
        self.downloaded = 0
        self.uploaded = 0

    def add_piece(self, index, data):
        if index in self.pieces:
            return  # Already have this piece
        expected_hash = self.get_piece_hash(index)
        actual_hash = hashlib.sha1(data).digest()
        if actual_hash == expected_hash:
            self.pieces[index] = data
            self.missing_pieces.remove(index)
            self.downloaded += len(data)
            print(f"Piece {index} verified and added.")
        else:
            print(f"Piece {index} failed hash check.")

    def get_piece(self, index):
        return self.pieces.get(index)

    def get_piece_hash(self, index):
        start = index * 20  # Each SHA-1 hash is 20 bytes
        end = start + 20
        return self.metainfo[b'info'][b'pieces'][start:end]

    def next_missing_piece(self):
        if self.missing_pieces:
            return min(self.missing_pieces)
        else:
            return None

    def is_complete(self):
        return len(self.missing_pieces) == 0

    def reconstruct_file(self, output_path):
        with open(output_path, 'wb') as outfile:
            for index in range(self.total_pieces):
                piece_data = self.pieces.get(index)
                if piece_data is not None:
                    outfile.write(piece_data)
                else:
                    print(f"Missing piece {index}, cannot reconstruct file.")
                    return
        print(f"File reconstructed at {output_path}")

    def load_pieces_from_file(self, file_path):
        with open(file_path, 'rb') as f:
            for index in range(self.total_pieces):
                piece_data = f.read(self.piece_length)
                if not piece_data:
                    break
                self.pieces[index] = piece_data
                self.missing_pieces.discard(index)
        print(f"Loaded {len(self.pieces)} pieces from file.")

