from stem import SocketError
from stem.control import Controller
import os.path
import random
class RelayList():
    def __init__(self, conf, logger):
        self._conf = conf
        self._log = logger
        self._pairs = set()
        self._max_pairs = conf.getint('relaylist','max_pairs')
        if self._max_pairs < 0: self._max_pairs = 1000000000000
        source = conf['relaylist']['source']
        if source == 'file':
            fname = conf['relaylist']['filename']
            return self._init_from_file(fname)
        elif source == 'internet': return self._init_from_internet()
        else:
            self._fail_hard('unknown source: {}. Failing'.format(source))
    def __iter__(self):
        return self._pairs.__iter__()

    def __len__(self):
        return len(self._pairs)

    def _init_from_file(self, fname):
        if not os.path.isfile(fname):
            self._fail_hard('{} doesn\'t exist. Failing.')
        self._log.notice('Initializing RelayList from {}'.format(fname))
        self._pairs = set()
        with open(fname, 'rt') as f:
            for line in f:
                #line = line[:-1] # trailing newline
                line = line.strip()
                if len(line) <= 0: continue # empty line
                if line[0] == '#': continue # comment
                fp1, fp2 = line.split(' ')
                assert len(fp1) == 40
                assert len(fp2) == 40
                self._pairs.add( (fp1, fp2) )
                if len(self._pairs) >= self._max_pairs: break
        self._log.notice('Finished reading {} relay pairs from file'.format(
            len(self._pairs)))
        if len(self._pairs) >= self._max_pairs:
            self._log.warn('We stopped reading {} because we hit our '
                'configured maximimum number of relay pairs'.format(fname))

    def _init_from_internet(self):
        self._log.notice('Initializing RelayList from the current consensus')
        cont = None
        ctrl_port = self._conf.getint('torclient','ctrl_port')
        try:
            cont = Controller.from_port(port=ctrl_port)
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
        relays = cont.get_network_statuses()
        all_fps = set([ r.fingerprint for r in relays if not r.is_unmeasured ])
        ###
        # simple method
        ###
        #for fp1 in all_fps:
        #    for fp2 in all_fps:
        #        if fp1 == fp2: continue
        #        self._pairs.add( (fp1, fp2) )
        #        if len(self._pairs) >= self._max_pairs: break
        #    if len(self._pairs) >= self._max_pairs: break
        ###
        # beter? method
        ###
        while len(self._pairs) < self._max_pairs:
            self._pairs.add( tuple(random.sample(all_fps, 2)) )
        self._log.notice('Finished reading {} relay pairs from the current '
                'consensus'.format(len(self._pairs)))
        if len(self._pairs) >= self._max_pairs:
            self._log.warn('We stopped adding relay pairs because we hit our '
                'configured maximimum')


    def _fail_hard(self, msg):
        self._log.error(msg)
        exit(1)
