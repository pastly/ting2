from stem import ( CircuitExtensionFailed, DescriptorUnavailable,
        InvalidRequest, SocketError
)
from stem.control import Controller, EventType
import socks # PySocks
import socket
import time

class TingClient():
    def __init__(self, conf, logger, stream_creation_lock):
        self._conf = conf
        self._log = logger
        self._stream_creation_lock = stream_creation_lock
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
        cont.set_conf('LearnCircuitBuildTimeout','0')
        cont.set_conf('CircuitBuildTimeout','10')
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
        relay_nicks = []
        attempts = self._conf.getint('torclient','circ_build_attempts')
        for fp in path:
            n = '(unknown)'
            try: n = self._cont.get_network_status(fp).nickname
            except DescriptorUnavailable: n = fp[0:8]
            relay_nicks.append(n)
        while attempts > 0:
            try:
                attempts -= 1
                log.info('Building circ: {}'.format('->'.join(relay_nicks)))
                circ_id = self._cont.new_circuit(path, await_build=True)
            except (InvalidRequest, CircuitExtensionFailed) as e:
                log.warn('Failed to build circ: {}'.format(e))
            else:
                log.debug('Built circ {} {}'.format(circ_id,
                    '->'.join(relay_nicks)))
                return circ_id
        return None

    def _close_circ(self, circ_id):
        log = self._log
        if self._cont.get_circuit(circ_id, default=None):
            self._cont.close_circuit(circ_id)

    def ting(self, circ_id):
        log = self._log
        host = self._conf['ting']['target_host']
        port = self._conf.getint('ting','target_port')
        num_samples = eval(self._conf['ting']['num_samples'])
        log.debug('Waiting for lock to create stream')
        self._stream_creation_lock.acquire()
        log.debug('Received lock')
        stream_event_listener = self._stream_event_listener(circ_id)
        self._cont.add_event_listener(stream_event_listener, EventType.STREAM)
        s = self._new_socket()
        try:
            log.info('Attempting connection to {}:{} through socks5 proxy'\
                .format(host, port))
            s.connect( (host, port) )
            self._cont.remove_event_listener(stream_event_listener)
        except (socks.ProxyConnectionError, socks.GeneralProxyError) as e:
            log.warn('Couldn\'t connect to {}:{} through socks5 proxy: {}'\
                .format(host,port,e))
            self._cont.remove_event_listener(stream_event_listener)
            self._stream_creation_lock.release()
            log.debug('Released lock to create stream')
        else:
            self._cont.remove_event_listener(stream_event_listener)
            self._stream_creation_lock.release()
            log.debug('Released lock to create stream')
            msg, done = b'!', b'X'
            log.info('Sending {} tings on circ {}'.format(num_samples, circ_id))
            samples = []
            try:
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
            except (BrokenPipeError, socket.timeout):
                log.warn("Failed to measure over circ {} due to timeout or "
                    "a broken pipe".format(circ_id))
                return None
        finally:
            s.close()

    def _rtt_on(self, path):
        attempts = self._conf.getint('ting','measurement_attempts')
        circ_id = self._build_circ(path)
        if circ_id == None: return None
        for _ in range(0,attempts):
            rtt = self.ting(circ_id)
            if rtt != None: break
        self._close_circ(circ_id)
        return rtt

    def _create_result(self, rtt, fp1, fp2):
        return {
                'rtt': rtt,
                'x': fp1, 'y': fp2,
                'time': time.time()
        }

    def perform_on(self, target1_fp, target2_fp):
        w = self._conf['ting']['relay1_fp']
        x, y = target1_fp, target2_fp
        z = self._conf['ting']['relay2_fp']
        wxyz_rtt, wxz_rtt, wyz_rtt = None, None, None

        wxyz_rtt = self._rtt_on([w,x,y,z])
        if wxyz_rtt == None: return self._create_result(None, x, y)

        wxz_rtt = self._rtt_on([w,x,z])
        if wxz_rtt == None: return self._create_result(None, x, y)

        wyz_rtt = self._rtt_on([w,y,z])
        if wyz_rtt == None: return self._create_result(None, x, y)

        xy_rtt = wxyz_rtt - 0.5*wxz_rtt - 0.5*wyz_rtt
        return self._create_result(xy_rtt, x, y)

    def _stream_event_listener(self, circ_id):
        log = self._log
        def closure_stream_event_listener(st):
            if st.status == 'NEW' and st.purpose == 'USER':
                log.debug('Attaching stream {} to circ {}'.format(
                    st.id, circ_id))
                self._cont.attach_stream(st.id, circ_id)
            else:
                #log.debug('Ignoring {}'.format(st))
                pass
        return closure_stream_event_listener
