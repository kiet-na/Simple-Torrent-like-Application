# tracker_server.py

from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import json

class TrackerHandler(BaseHTTPRequestHandler):
    peers = {}  # Dictionary mapping info_hash to peer dictionaries

    def do_GET(self):
        if self.path.startswith('/announce'):
            self.handle_announce()
        else:
            self.send_error(404, "File not found.")

    def handle_announce(self):
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        info_hash = params.get('info_hash', [None])[0]
        peer_id = params.get('peer_id', [None])[0]
        ip = self.client_address[0]
        port = params.get('port', [None])[0]
        event = params.get('event', [None])[0]

        if None in (info_hash, peer_id, port):
            self.send_error(400, "Missing required parameters.")
            return

        port = int(port)

        if info_hash not in self.peers:
            self.peers[info_hash] = {}

        if event == 'started':
            self.peers[info_hash][peer_id] = {'peer_id': peer_id, 'ip': ip, 'port': port}
        elif event == 'stopped':
            if peer_id in self.peers[info_hash]:
                del self.peers[info_hash][peer_id]
        elif event == 'completed':
            pass  # Handle 'completed' event if necessary

        # Prepare response, excluding the requesting peer
        peers_list = [
            peer_info for pid, peer_info in self.peers[info_hash].items()
            if pid != peer_id
        ]

        response = {
            'interval': 1800,
            'peers': peers_list
        }

        response_data = json.dumps(response).encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(response_data)))
        self.end_headers()
        self.wfile.write(response_data)

def run_tracker(server_class=HTTPServer, handler_class=TrackerHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Tracker Server running at port {port}...")
    httpd.serve_forever()

if __name__ == '__main__':
    run_tracker()
