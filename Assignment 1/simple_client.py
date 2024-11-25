import socket

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect(('127.0.0.1', 6881))
client_socket.sendall(b"Hello, Server!")
data = client_socket.recv(1024)
print(f"Received data: {data}")
client_socket.close()
