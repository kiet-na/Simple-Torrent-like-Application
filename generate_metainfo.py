# generate_metainfo.py

import os
import hashlib
import bencodepy  # Ensure this is installed via 'pip install bencodepy'

def generate_metainfo(file_path, tracker_url, piece_length=512*1024):
    file_size = os.path.getsize(file_path)
    pieces = []

    with open(file_path, 'rb') as f:
        while True:
            piece = f.read(piece_length)
            if not piece:
                break
            piece_hash = hashlib.sha1(piece).digest()
            pieces.append(piece_hash)

    metainfo = {
        b'announce': tracker_url.encode('utf-8'),
        b'info': {
            b'name': os.path.basename(file_path).encode('utf-8'),
            b'piece length': piece_length,
            b'pieces': b''.join(pieces),
            b'length': file_size
        }
    }

    # Correctly write the bencoded data
    torrent_file_path = os.path.join('seeder_node', 'example.torrent')
    with open(torrent_file_path, 'wb') as tf:
        tf.write(bencodepy.encode(metainfo))

    print(f"Metainfo file generated at {torrent_file_path}")

if __name__ == '__main__':
    tracker_url = 'http://localhost:8000'
    file_path = 'seeder_node/test_file.txt'  # Update this path if necessary
    generate_metainfo(file_path, tracker_url)
