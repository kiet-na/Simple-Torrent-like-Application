# generate_metainfo.py

import os
import hashlib
import bencodepy

def collect_files(directory):
    file_info_list = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        files.sort()
        for file in files:
            if file.startswith('.'):
                continue
            if file == 'example.torrent':
                continue  # Skip the metainfo file itself
            file_path = os.path.join(root, file)
            file_length = os.path.getsize(file_path)
            relative_path = os.path.relpath(file_path, directory)
            path_components = relative_path.split(os.sep)
            file_info_list.append({
                'length': file_length,
                'path': [component.encode('utf-8') for component in path_components],
                'relative_path': relative_path
            })
    # Sort the file_info_list based on the relative_path to ensure consistent order
    file_info_list.sort(key=lambda x: x['relative_path'])

    # Print the sorted file paths
    print("Files in generate_metainfo.py:")
    for file_info in file_info_list:
        print(file_info['relative_path'])
    return file_info_list

def generate_metainfo(directory, tracker_url, piece_length=512*1024):
    files = collect_files(directory)
    total_size = sum(file['length'] for file in files)
    pieces = []

    # Read all files sequentially to generate pieces
    with open('combined_files.tmp', 'wb') as tmp_file:
        for file_info in files:
            file_path = os.path.join(directory, *[part.decode('utf-8') for part in file_info['path']])
            with open(file_path, 'rb') as f:
                tmp_file.write(f.read())

    # Generate pieces from the combined file
    with open('combined_files.tmp', 'rb') as f:
        piece_index = 0
        while True:
            piece = f.read(piece_length)
            if not piece:
                break
            piece_hash = hashlib.sha1(piece).digest()  # Use raw bytes
            pieces.append(piece_hash)
            print(f"Generated Piece {piece_index} length: {len(piece)}")
            piece_index += 1

    os.remove('combined_files.tmp')  # Clean up the temporary file

    metainfo = {
        b'announce': tracker_url.encode('utf-8'),
        b'info': {
            b'name': os.path.basename(directory).encode('utf-8'),
            b'piece length': piece_length,
            b'pieces': b''.join(pieces),
            b'files': [
                {
                    b'length': file['length'],
                    b'path': file['path']
                } for file in files
            ]
        }
    }

    # Write the metainfo to a .torrent file
    torrent_file_path = os.path.join(directory, 'example.torrent')
    with open(torrent_file_path, 'wb') as tf:
        tf.write(bencodepy.encode(metainfo))

    print(f"Metainfo file generated at {torrent_file_path}")
    # After generating all pieces
    print(f"Total number of pieces: {len(pieces)}")

if __name__ == '__main__':
    tracker_url = 'http://localhost:8000'
    directory = 'seeder_node/files'  # Directory containing multiple files
    generate_metainfo(directory, tracker_url)
