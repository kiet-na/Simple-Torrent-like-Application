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
            # Encode each path component to bytes
            path_components_bytes = [component.encode('utf-8') for component in path_components]
            files.append({
                b'length': length,
                b'path': path_components_bytes
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
        filepath = os.path.join(directory_path, *[component.decode('utf-8') for component in file_info[b'path']])
        with open(filepath, 'rb') as f:
            file_contents += f.read()

    # Calculate piece hashes
    for i in range(0, len(file_contents), piece_length):
        piece = file_contents[i:i + piece_length]
        pieces += sha1_hash(piece)

    # Construct the torrent dictionary with byte string keys and values
    torrent = {
        b'announce': tracker_url.encode('utf-8'),
        b'info': {
            b'name': os.path.basename(directory_path).encode('utf-8'),
            b'piece length': piece_length,
            b'pieces': pieces,
            b'files': files_info
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
