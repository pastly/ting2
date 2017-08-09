from stem import ( CircuitExtensionFailed, DescriptorUnavailable,
        InvalidRequest, SocketError
)
from stem.control import Controller, EventType
import socks # PySocks
import socket
import time

class TingClient():
    def __init__(self, args, logger, stream_creation_lock, cache_dict):
        self._args = args
        self._log = logger
        self._stream_creation_lock = stream_creation_lock
        self._cache_dict, self._cache_dict_lock = cache_dict
        self._cont = \
            self._init_controller(args.ctrl_port)

    def _fail_hard(self, msg):
        log = self._log
        if msg: log.error(msg)
        exit(1)

    def _path_to_nicks(self, path):
        relay_nicks = []
        for fp in path:
            n = '(unknown)'
            try: n = self._cont.get_network_status(fp).nickname
            except DescriptorUnavailable: n = fp[0:8]
            relay_nicks.append(n)
        return relay_nicks

    def _init_controller(self, port):
        log = self._log
        log.info('Initiazling Tor controller')
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
        args = self._args
        socks_host = args.socks_host
        socks_port = args.socks_port
        socks_timeout = args.socks_timeout
        log.info('Creating socket through socks5 proxy at {}:{}'.format(
            socks_host, socks_port))
        s = socks.socksocket()
        s.set_proxy(socks.PROXY_TYPE_SOCKS5, socks_host, socks_port)
        s.settimeout(socks_timeout)
        return s

    def _build_circ(self, path):
        log = self._log
        relay_nicks = self._path_to_nicks(path)
        attempts = self._args.circ_build_attempts
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
        host = self._args.target_host
        port = self._args.target_port
        num_samples = self._args.samples
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
                try: s.shutdown(socket.SHUT_RDWR)
                except: pass
                log.info('Min RTT: {}'.format(min(samples)))
                return min(samples)
            except (BrokenPipeError, socket.timeout):
                log.warn("Failed to measure over circ {} due to timeout or "
                    "a broken pipe".format(circ_id))
                return None
        finally:
            s.close()

    def _get_rtt_on(self, path):
        cached_rtt = self._get_cached_rtt(path)
        if cached_rtt != None:
            relay_nicks = self._path_to_nicks(path)
            self._log.info('Using cached RTT of {} for {}'.format(
                cached_rtt, '->'.join(relay_nicks)))
            return cached_rtt
        attempts = self._args.measurement_attempts
        circ_id = self._build_circ(path)
        if circ_id == None: return None
        for _ in range(0,attempts):
            rtt = self.ting(circ_id)
            if rtt != None: break
        self._close_circ(circ_id)
        return rtt

    def _create_result(self, rtt, fp1, fp2):
        ip1, ip2 = ['0.0.0.0'] * 2
        nick1, nick2 = ['(unknown)'] * 2
        try: ns1 = self._cont.get_network_status(fp1)
        except DescriptorUnavailable: pass
        else: ip1, nick1 = ns1.address, ns1.nickname
        try: ns2 = self._cont.get_network_status(fp2)
        except DescriptorUnavailable: pass
        else: ip2, nick2 = ns2.address, ns2.nickname
        return {
                'time': time.time(),
                'rtt': rtt,
                'x': { 'fp': fp1, 'ip': ip1, 'nick': nick1, },
                'y': { 'fp': fp2, 'ip': ip2, 'nick': nick2, },
        }

    def _create_rtt_cache_entry(self, rtt, path):
        self._log.info('Caching RTT of {} for {}'.format(
            rtt, '->'.join(self._path_to_nicks(path))))
        return {
                'rtt': rtt,
                'path': path,
                'time': time.time()
        }

    def _cache_rtt(self, rtt, path):
        assert len(path) == 3 or len(path) == 4
        if len(path) == 3:
            if not self._args.cache_3hop: return
            lifetime = self._args.cache_3hop_life
        else:
            if not self._args.cache_4hop: return
            lifetime = self._args.cache_4hop_life
        key = '-'.join(path)
        self._cache_dict_lock.acquire()
        cache_dict = self._cache_dict
        if key not in cache_dict:
            cache_dict[key] = self._create_rtt_cache_entry(rtt, path)
        else:
            now = time.time()
            cached_at = cache_dict[key]['time']
            if cached_at + lifetime <= now or \
                cache_dict[key]['rtt'] > rtt:
                cache_dict[key] = self._create_rtt_cache_entry(rtt, path)
        self._cache_dict_lock.release()

    def _get_cached_rtt(self, path):
        if len(path) == 3:
            if not self._args.cache_3hop: return None
            lifetime = self._args.cache_3hop_life
        else:
            if not self._args.cache_4hop: return None
            lifetime = self._args.cache_4hop_life
        key = '-'.join(path)
        cache_dict = self._cache_dict
        self._cache_dict_lock.acquire()
        if key not in cache_dict: rtt = None
        else:
            now = time.time()
            cached_at = cache_dict[key]['time']
            if cached_at + lifetime < now: rtt = None
            else: rtt = cache_dict[key]['rtt']
        self._cache_dict_lock.release()
        return rtt

    def perform_on(self, target1_fp, target2_fp):
        w = self._args.w_relay
        x, y = target1_fp, target2_fp
        z = self._args.z_relay
        wxyz_rtt, wxz_rtt, wyz_rtt = None, None, None

        path = [w,x,y,z]
        wxyz_rtt = self._get_rtt_on(path)
        if wxyz_rtt == None: return self._create_result(None, x, y)
        else: self._cache_rtt(wxyz_rtt, path)

        path = [w,x,z]
        wxz_rtt = self._get_rtt_on(path)
        if wxz_rtt == None: return self._create_result(None, x, y)
        else: self._cache_rtt(wxz_rtt, path)

        path = [w,y,z]
        wyz_rtt = self._get_rtt_on(path)
        if wyz_rtt == None: return self._create_result(None, x, y)
        else: self._cache_rtt(wyz_rtt, path)

        xy_rtt = wxyz_rtt - 0.5*wxz_rtt - 0.5*wyz_rtt
        return self._create_result(xy_rtt, x, y)

    def _stream_event_listener(self, circ_id):
        log = self._log
        def closure_stream_event_listener(st):
            if st.status == 'NEW' and st.purpose == 'USER':
                log.debug('Attaching stream {} to circ {}'.format(
                    st.id, circ_id))
                try:
                    self._cont.attach_stream(st.id, circ_id)
                except InvalidRequest as e:
                    log.warn('Couldn\'t attach stream to circ {}: {}'.format(
                        circ_id, e))
            else:
                #log.debug('Ignoring {}'.format(st))
                pass
        return closure_stream_event_listener
