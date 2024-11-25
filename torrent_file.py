# torrent_file.py
import json
from metainfo_file import MetainfoFile

class TorrentFile:
    def __init__(self, metainfo):
        self.metainfo = metainfo

    @staticmethod
    def from_file(file_path):
        with open(file_path, 'r') as f:
            data = json.load(f)
            metainfo = MetainfoFile.from_dict(data)
            return TorrentFile(metainfo)
