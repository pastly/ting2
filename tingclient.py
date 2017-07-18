from stem import SocketError
from stem.control import Controller, EventType
import socks # PySocks
import socket
import time

class TingClient():
    def __init__(self, conf, logger):
        self._conf = conf
        self._log = logger
        self._cont = \
            self._init_controller(conf.getint('torclient','ctrl_port'))

    def _fail_hard(self, msg):
        log = self._log
        if msg: log.error(msg)
        exit(1)

    def _init_controller(self, port):
        log = self._log
        log.notice('Initiazling Tor controller')
        try:
            cont = Controller.from_port(port=port)
        except SocketError:
            self._fail_hard('SocketError: Couldn\'t connect to Tor control "\
                "port {}'.format(port))
        if not cont:
            self._fail_hard('Couldn\'t connect to Tor control port {}'\
                .format(port))
        if not cont.is_authenticated(): cont.authenticate()
        if not cont.is_authenticated():
            self._fail_hard('Couldn\'t authenticate to Tor control port {}'\
                .format(port))
        cont.set_conf('__DisablePredictedCircuits', '1')
        cont.set_conf('__LeaveStreamsUnattached', '1')
        return cont

    def _new_socket(self):
        log = self._log
        conf = self._conf
        socks_host = conf['torclient']['socks_host']
        socks_port = conf.getint('torclient','socks_port')
        socks_timeout = eval(conf['torclient']['socks_timeout'])
        log.info('Creating socket through socks5 proxy at {}:{}'.format(
            socks_host, socks_port))
        s = socks.socksocket()
        s.set_proxy(socks.PROXY_TYPE_SOCKS5, socks_host, socks_port)
        s.settimeout(socks_timeout)
        return s

    def _build_circ(self, path):
        log = self._log
        log.info('Building circ: {}'.format(
            ' -> '.join([p[0:8] for p in path])))
        circ_id = self._cont.new_circuit(path, await_build=True)
        return circ_id

    def _close_circ(self, circ_id):
        log = self._log
        if self._cont.get_circuit(circ_id, default=None):
            self._cont.close_circuit(circ_id)

    def ting(self, circ_id):
        log = self._log
        host = self._conf['ting']['target_host'] 
        port = self._conf.getint('ting','target_port')
        num_samples = eval(self._conf['ting']['num_samples'])
        stream_event_listener = self._stream_event_listener(circ_id)
        self._cont.add_event_listener(stream_event_listener, EventType.STREAM)
        s = self._new_socket()
        try:
            log.info('Attempting connection to {}:{} through socks5 proxy'\
                .format(host, port))
            s.connect( (host, port) )
        except (socks.ProxyConnectionError, socks.GeneralProxyError) as e:
            log.warn('Couldn\'t connect to {}:{} through socks5 proxy: {}'\
                .format(host,port,e))
        else:
            msg, done = b'!', b'X'
            log.info('Sending {} tings'.format(num_samples))
            samples = []
            for _ in range(0,num_samples):
                start = time.time()
                s.send(msg)
                _ = s.recv(1)
                end = time.time()
                samples.append(end-start)
            s.send(done)
            s.shutdown(socket.SHUT_RDWR)
            log.info('Min RTT: {}'.format(min(samples)))
            return min(samples)
        finally:
            s.close()
            self._cont.remove_event_listener(stream_event_listener)

    def tmp_test(self):
        log = self._log
        w = self._conf['ting']['relay1_fp']
        x = '335746A6DEB684FABDF3FC5835C3898F05C5A5A8'
        y = '91516595837183D9ECD1318D00723A8676F4731C'
        z = self._conf['ting']['relay2_fp']
        path = [w,x,y,z]
        circ_id = self._build_circ(path)
        wxyz_rtt = self.ting(circ_id)
        self._close_circ(circ_id)
        path = [w,x,z]
        circ_id = self._build_circ(path)
        wxz_rtt = self.ting(circ_id)
        self._close_circ(circ_id)
        path = [w,y,z]
        circ_id = self._build_circ(path)
        wyz_rtt = self.ting(circ_id)
        self._close_circ(circ_id)
        xy_rtt = wxyz_rtt - 0.5*wxz_rtt - 0.5*wyz_rtt
        xy_rtt *= 1000
        log.notice('RTT xy: {}'.format(round(xy_rtt,2)))

    def _stream_event_listener(self, circ_id):
        log = self._log
        def closure_stream_event_listener(st):
            if st.status == 'NEW' and st.purpose == 'USER':
                log.debug('Attaching stream {} to circ {}'.format(
                    st.id, circ_id))
                self._cont.attach_stream(st.id, circ_id)
            else:
                log.debug('Ignoring {}'.format(st))
        return closure_stream_event_listener
