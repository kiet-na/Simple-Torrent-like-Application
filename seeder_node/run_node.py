# run_node.py

import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from node_client import NodeClient

if __name__ == '__main__':
    tracker_url = 'http://localhost:8000'
    listening_port = 6881
    role = 'seeder'
    node = NodeClient(tracker_url=tracker_url, listening_port=listening_port, role=role)
    node.start()
