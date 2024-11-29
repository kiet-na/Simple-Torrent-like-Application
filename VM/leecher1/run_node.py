# run_node.py

import argparse
import os
from node_client import NodeClient

def main():
    parser = argparse.ArgumentParser(description='Simple BitTorrent Client')
    parser.add_argument('torrent_file', help='Path to the .torrent file')
    parser.add_argument('-p', '--port', type=int, default=6881, help='Port to listen on (default: 6881)')
    parser.add_argument('-o', '--output', default='downloads', help='Output directory for downloaded files (default: ./downloads)')
    parser.add_argument('-d', '--max-download', type=int, default=0, help='Maximum download speed (kB/s, 0 for unlimited)')
    parser.add_argument('-u', '--max-upload', type=int, default=0, help='Maximum upload speed (kB/s, 0 for unlimited)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--role', choices=['seeder', 'leecher'], default='leecher', help='Role of the client (default: leecher)')
    args = parser.parse_args()

    # Ensure output directory exists
    if not os.path.exists(args.output):
        os.makedirs(args.output)

    # Initialize NodeClient with the provided arguments
    client = NodeClient(
        torrent_file=args.torrent_file,
        listen_port=args.port,
        download_directory=args.output,
        max_download_speed=args.max_download * 1024,  # Convert kB/s to bytes/s
        max_upload_speed=args.max_upload * 1024,      # Convert kB/s to bytes/s
        verbose=args.verbose,
        role=args.role
    )
    client.start()

if __name__ == '__main__':
    main()
