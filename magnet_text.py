# magnet_text.py

class MagnetText:
    def __init__(self, hash_code):
        self.hash_code = hash_code  # Unique identifier for the torrent

    def get_metainfo_url(self, tracker_url):
        return f"{tracker_url}/metainfo/{self.hash_code}"
