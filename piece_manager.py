# piece_manager.py

import hashlib

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
        self.requested_pieces = set()
        self.piece_availability = [0] * self.total_pieces

    def add_piece(self, index, data):
        if index in self.pieces:
            return  # Already have this piece
        expected_hash = self.get_piece_hash(index)
        actual_hash = hashlib.sha1(data).digest()
        if actual_hash == expected_hash:
            self.pieces[index] = data
            self.missing_pieces.remove(index)
            self.requested_pieces.discard(index)
            self.downloaded += len(data)
            print(f"Piece {index} verified and added.")
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

    def update_piece_availability(self, peer_bitfield):
        for index in range(self.total_pieces):
            if self.has_piece_in_bitfield(peer_bitfield, index):
                self.piece_availability[index] += 1

    def has_piece_in_bitfield(self, bitfield, index):
        byte_index = index // 8
        bit_index = index % 8
        if byte_index >= len(bitfield):
            return False
        return (bitfield[byte_index] >> (7 - bit_index)) & 1

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

