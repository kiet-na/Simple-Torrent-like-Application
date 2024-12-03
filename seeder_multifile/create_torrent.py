# create_torrent.py

import bencodepy
import hashlib
import sys
import os

def sha1_hash(data):
    hasher = hashlib.sha1()
    hasher.update(data)
    return hasher.digest()

def get_files_info(base_path):
    files = []
    for root, dirs, filenames in os.walk(base_path):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            length = os.path.getsize(filepath)
            # Get the relative path components
            relative_path = os.path.relpath(filepath, base_path)
            path_components = relative_path.split(os.sep)
            files.append({
                'length': length,
                'path': path_components
            })
    return files

def create_torrent(directory_path, tracker_url, torrent_path):
    piece_length = 524288  # 512 KB
    pieces = b''

    # Get all files in the directory
    files_info = get_files_info(directory_path)

    # Read all files and compute piece hashes
    file_contents = b''
    for file_info in files_info:
        filepath = os.path.join(directory_path, *file_info['path'])
        with open(filepath, 'rb') as f:
            file_contents += f.read()

    # Calculate piece hashes
    for i in range(0, len(file_contents), piece_length):
        piece = file_contents[i:i + piece_length]
        pieces += sha1_hash(piece)

    torrent = {
        'announce': tracker_url,
        'info': {
            'name': os.path.basename(directory_path),
            'piece length': piece_length,
            'pieces': pieces,
            'files': files_info
        }
    }

    with open(torrent_path, 'wb') as tf:
        tf.write(bencodepy.encode(torrent))

    print(f"Created multi-file torrent at {torrent_path}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python create_torrent.py <directory_path> <tracker_url> <torrent_path>")
        sys.exit(1)
    directory_path = sys.argv[1]
    tracker_url = sys.argv[2]
    torrent_path = sys.argv[3]
    create_torrent(directory_path, tracker_url, torrent_path)