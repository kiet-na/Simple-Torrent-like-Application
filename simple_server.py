import socket

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('127.0.0.1', 6881))
server_socket.listen(1)
print("Server listening on port 6881")

conn, addr = server_socket.accept()
print(f"Accepted connection from {addr}")
data = conn.recv(1024)
print(f"Received data: {data}")
conn.sendall(b"ACK")
conn.close()
server_socket.close()
