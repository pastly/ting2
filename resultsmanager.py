from stem import ( CircuitExtensionFailed, DescriptorUnavailable,
        InvalidRequest, SocketError
)
from stem.control import Controller, EventType
import json, time
from threading import Thread
from queue import Empty, Queue
class ResultsManager():
    def __init__(self, args, logger, end_event):
        self._args = args
        self._log = logger
        self._cont = \
            self._init_controller(args.ctrl_port)
        self._write_results_every = args.write_results_every
        self._results_fname = args.out_result_file
        self._incoming_queue = Queue()
        self._is_shutting_down = end_event
        Thread(target=self._loop_forever, name='results').start()

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
        return cont

    def add_result(self, result):
        self._incoming_queue.put(result)

    def make_result(self, rtt, fp1, fp2):
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

    def _loop_forever(self):
        pending_results = []
        while not self._is_shutting_down.is_set():
            res = None
            try: res = self._incoming_queue.get(timeout=1)
            except Empty:
                self._log.debug('No pending results')
                continue
            self._log.debug('Got',res)
            pending_results.append(res)
            if len(pending_results) >= self._write_results_every:
                self._write_results(pending_results)
                pending_results = []
        if len(pending_results) > 0: self._write_results(pending_results)
        pending_results = []

    def _write_results(self, results):
        self._log.notice('Collected',len(results),'results so writing them to',
                self._results_fname)
        with open(self._results_fname, 'at') as f:
            output = '\n'.join([json.dumps(r) for r in results])
            f.write('{}\n'.format(output))
