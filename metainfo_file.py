# metainfo_file.py
import hashlib
import json

class MetainfoFile:
    def __init__(self, info, announce, piece_length, pieces, files):
        self.info = info
        self.announce = announce
        self.piece_length = piece_length
        self.pieces = pieces  # List of piece hashes
        self.files = files  # List of files in the torrent
        self.info_hash = self.calculate_info_hash()
        self.total_length = sum(file['length'] for file in files)

    def calculate_info_hash(self):
        info_json = json.dumps(self.info, sort_keys=True).encode('utf-8')
        return hashlib.sha1(info_json).hexdigest()

    @staticmethod
    def from_dict(data):
        info = data['info']
        announce = data['announce']
        piece_length = info['piece length']
        pieces = info['pieces']
        files = info['files'] if 'files' in info else [{'length': info['length'], 'path': info['name']}]
        return MetainfoFile(info, announce, piece_length, pieces, files)