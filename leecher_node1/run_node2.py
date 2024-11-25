# run_node2.py

import sys
import os

# Add the parent directory to Python path if shared modules are in the parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from node_client import NodeClient

if __name__ == '__main__':
    tracker_url = 'http://localhost:8000'
    listening_port = 6883
    role = 'leecher'
    leecher = NodeClient(tracker_url, listening_port, role)
    leecher.start()

