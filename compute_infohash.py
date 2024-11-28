# compute_info_hash.py

import bencodepy
import hashlib
import sys

def compute_info_hash(torrent_path):
    with open(torrent_path, 'rb') as tf:
        metainfo = bencodepy.decode(tf.read())
    info = metainfo[b'info']
    encoded_info = bencodepy.encode(info)
    info_hash = hashlib.sha1(encoded_info).digest()
    print(f"Info Hash: {info_hash.hex()}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python compute_info_hash.py <torrent_path>")
        sys.exit(1)
    torrent_path = sys.argv[1]
    compute_info_hash(torrent_path)
