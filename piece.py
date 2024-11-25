# piece.py

class Piece:
    def __init__(self, index, hash_value, data=None):
        self.index = index
        self.hash_value = hash_value  # Hash of the piece data
        self.data = data  # Actual data of the piece
        self.is_downloaded = data is not None

    def verify(self):
        # Verify piece integrity by checking hash
        pass