#!/usr/bin/env python3
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
from datetime import datetime
import os
import socket

# based on https://gist.github.com/fuentesjr/240063
# which is based on [...]

def log(*msg):
    ts = '[{}]'.format(datetime.now())
    if msg: print(ts,*msg)
def warn(*msg):
    if msg: log('[WARN]',*msg)
def fail_hard(*msg):
    if msg: log('[ERROR]',*msg)
    exit(1)

def child_proc(pid, acceptor, listen_ip, listen_port):
    log('Child {} listening on {}:{}'.format(pid, listen_ip, listen_port))
    try:
        while True:
            conn, addr = acceptor.accept()
            log('[{}]'.format(pid),'Accepted connection from',addr)
            data = conn.recv(1)
            while data and data != b'X':
                try:
                    conn.send(data)
                    data = conn.recv(1)
                except ConnectionResetError as e:
                    log(e)
                    break
            conn.close()
            log('[{}]'.format(pid),'Connection closed.')
    except KeyboardInterrupt:
        exit(0)

def main(args):
    acceptor = socket.socket()
    listen_ip = args.listen_ip
    listen_port = args.listen_port
    listen_queue = args.pending_connections
    max_concurrent_clients = args.concurrent_connections
    acceptor.bind((listen_ip, listen_port))
    acceptor.listen(listen_queue)

    for i in range(max_concurrent_clients):
        pid = os.fork()
        if pid == 0: child_proc(os.getpid(), acceptor, listen_ip, listen_port)

    try:
        log('All forked! Now waiting.')
        os.waitpid(-1, 0)
    except KeyboardInterrupt:
        log('\nExiting')
    finally:
        acceptor.close()
        exit(0)

if __name__=='__main__':
    parser = ArgumentParser(
            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--listen-ip', help='bind here', type=str,
            default='0.0.0.0')
    parser.add_argument('--listen-port', help='bind here', type=int,
            default=16667)
    parser.add_argument('--pending-connections', help='size of incoming queue',
            type=int, default=30)
    parser.add_argument('--concurrent-connections', type=int, default=100,
            help='num clients to handle at once')
    args = parser.parse_args()
    exit(main(args))
