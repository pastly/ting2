#!/usr/bin/env python3
import os
import socket

# based on https://gist.github.com/fuentesjr/240063
# which is based on [...]

acceptor = socket.socket()
listen_ip = '216.218.222.14'
listen_port = 16667
listen_queue = 30
max_concurrent_clients = 100
acceptor.bind((listen_ip, listen_port))
acceptor.listen(listen_queue)

def child_proc(pid):
    print('Child {} listening on {}:{}'.format(pid, listen_ip, listen_port))
    try:
        while True:
            conn, addr = acceptor.accept()
            print('[',pid,'] Accepted connection from',addr)
            data = conn.recv(1)
            while data and data != b'X':
                conn.send(data)
                data = conn.recv(1)
            conn.close()
            print('[',pid,'] Connection closed.')
    except KeyboardInterrupt:
        exit(0)

for i in range(max_concurrent_clients):
    pid = os.fork()
    if pid == 0: child_proc(os.getpid())

try:
    print('All forked! Now waiting.')
    os.waitpid(-1, 0)
except KeyboardInterrupt:
    print('\nExiting')
finally:
    acceptor.close()
    exit(0)
