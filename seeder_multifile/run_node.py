import argparse
import threading
from node_client import NodeClient
import sys
import time

# Track start time
start_time = time.time()

def command_ui(client):
    """Thread that handles command-line user input and interacts with the client."""
    print("Command UI started. Type 'help' for available commands.")
    while client.running:
        command = input("\n> ").strip().lower()
        if command == "help":
            print("Available commands:")
            print("  status     - Show download/upload progress and stats")
            print("  peers      - List currently connected peers")
            print("  pieces     - Show information about pieces (downloaded/missing)")
            print("  speed      - Show average download (and upload) speed from start")
            print("  stop       - Gracefully stop the client")
            print("  help       - Show this help message")
        elif command == "status":
            progress = 0.0
            if client.piece_manager.total_pieces > 0:
                progress = (len(client.piece_manager.pieces) / client.piece_manager.total_pieces) * 100

            downloaded = client.piece_manager.downloaded
            uploaded = client.piece_manager.uploaded
            print(f"Progress: {progress:.2f}%")
            print(f"Downloaded: {downloaded} bytes")
            print(f"Uploaded: {uploaded} bytes")

        elif command == "peers":
            # List connected peers
            with client.lock:
                if client.connected_peers:
                    print("Connected peers:")
                    for p in client.connected_peers:
                        print(f"{p.ip}:{p.port} - Choked: {p.peer_choking}, Interested: {p.peer_interested}")
                else:
                    print("No peers connected.")

        elif command == "pieces":
            total = client.piece_manager.total_pieces
            have = len(client.piece_manager.pieces)
            missing = total - have
            print(f"Total pieces: {total}, Have: {have}, Missing: {missing}")

        elif command == "speed":
            # Calculate average speeds since start
            elapsed = time.time() - start_time
            downloaded = client.piece_manager.downloaded
            uploaded = client.piece_manager.uploaded

            avg_download_speed = downloaded / elapsed if elapsed > 0 else 0
            avg_upload_speed = uploaded / elapsed if elapsed > 0 else 0

            print(f"Average Download Speed: {avg_download_speed:.2f} B/s")
            print(f"Average Upload Speed: {avg_upload_speed:.2f} B/s")

        elif command == "stop":
            client.stop()
            break
        else:
            print("Unknown command. Type 'help' for commands.")

def main():
    parser = argparse.ArgumentParser(description='Simple BitTorrent Client')
    parser.add_argument('torrent_file', help='Path to the .torrent file')
    parser.add_argument('-p', '--port', type=int, required=True, help='Port number to listen on')
    parser.add_argument('-o', '--output', required=True, help='Download directory')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--role', choices=['seeder', 'leecher'], default='leecher', help='Role of the peer')

    args = parser.parse_args()

    client = NodeClient(
        torrent_file=args.torrent_file,
        listen_port=args.port,
        download_directory=args.output,
        verbose=args.verbose,
        role=args.role
    )

    client_thread = threading.Thread(target=client.start, daemon=True)
    client_thread.start()

    try:
        command_ui(client)
    except KeyboardInterrupt:
        client.stop()

    client_thread.join()
    print("Client has stopped.")

if __name__ == '__main__':
    main()
