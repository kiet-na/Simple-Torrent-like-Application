# simple_tracker.py

from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse as urlparse
import bencodepy

class TrackerHandler(BaseHTTPRequestHandler):
    peers = []

    def do_GET(self):
        parsed_path = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(parsed_path.query)
        info_hash = query.get('info_hash', [None])[0]
        peer_id = query.get('peer_id', [None])[0]
        port = query.get('port', [None])[0]

        if info_hash and peer_id and port:
            # Add the peer to the list
            ip = self.client_address[0]
            peer = {'ip': ip, 'port': int(port), 'peer_id': peer_id}
            if peer not in self.peers:
                self.peers.append(peer)

            # Prepare the response
            response = {
                b'interval': 1800,
                b'peers': [{'ip': ip.encode('utf-8'), 'port': int(port)} for ip, port in [(p['ip'], p['port']) for p in self.peers if p['peer_id'] != peer_id]]
            }

            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(bencodepy.encode(response))
        else:
            self.send_response(400)
            self.end_headers()

def run_tracker(server_class=HTTPServer, handler_class=TrackerHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Tracker running on port {port}...")
    httpd.serve_forever()

if __name__ == '__main__':
    run_tracker()