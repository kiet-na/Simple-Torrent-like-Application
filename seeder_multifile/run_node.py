# run_node.py

import argparse
from node_client import NodeClient


def main():
    parser = argparse.ArgumentParser(description='Simple BitTorrent Client')
    parser.add_argument('torrent_file', help='Path to the .torrent file')
    parser.add_argument('-p', '--port', type=int, required=True, help='Port number to listen on')
    parser.add_argument('-o', '--output', required=True, help='Download directory')
    parser.add_argument('--max-download-speed', type=int, default=0, help='Max download speed in bytes per second')
    parser.add_argument('--max-upload-speed', type=int, default=0, help='Max upload speed in bytes per second')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--role', choices=['seeder', 'leecher'], default='leecher', help='Role of the peer')

    args = parser.parse_args()

    client = NodeClient(
        torrent_file=args.torrent_file,
        listen_port=args.port,
        download_directory=args.output,
        max_download_speed=args.max_download_speed,
        max_upload_speed=args.max_upload_speed,
        verbose=args.verbose,
        role=args.role
    )

    client.start()


if __name__ == '__main__':
    main()