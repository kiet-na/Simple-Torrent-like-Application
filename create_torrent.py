# create_torrent.py

import os
import bencodepy
import hashlib

def create_torrent(directory_path, tracker_url, torrent_path):
    files = []
    total_length = 0

    # Handle single and multi-file torrents
    if os.path.isdir(directory_path):
        for root, dirs, filenames in os.walk(directory_path):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                file_info = {
                    b'length': os.path.getsize(filepath),
                    b'path': [component.encode('utf-8') for component in os.path.relpath(filepath, directory_path).split(os.sep)]
                }
                files.append(file_info)
                total_length += file_info[b'length']
    else:
        file_info = {
            b'length': os.path.getsize(directory_path),
            b'name': os.path.basename(directory_path).encode('utf-8')
        }
        total_length = file_info[b'length']

    info = {
        b'name': os.path.basename(directory_path).encode('utf-8'),
        b'piece length': 524288,  # 512 KiB
    }

    if files:
        info[b'files'] = files
    else:
        info[b'length'] = total_length

    # Compute piece hashes
    # Implement piece hashing logic here if needed

    torrent = {
        b'announce': tracker_url.encode('utf-8'),
        b'info': info
    }

    with open(torrent_path, 'wb') as tf:
        tf.write(bencodepy.encode(torrent))
    print(f"Torrent file created at {torrent_path}")

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Create a .torrent file.')
    parser.add_argument('directory', help='Directory or file to create torrent from')
    parser.add_argument('tracker', help='Tracker URL (e.g., http://localhost:8000/announce)')
    parser.add_argument('output', help='Output torrent file path')

    args = parser.parse_args()
    create_torrent(args.directory, args.tracker, args.output)
