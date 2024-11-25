# utils.py
import random

def generate_peer_id():
    return '-STA0001-' + ''.join([str(random.randint(0, 9)) for _ in range(12)])
