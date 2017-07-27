from stem import SocketError
from stem.control import Controller
import os.path
import random
import time
import json
import lzma
import gzip
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
            self._init_from_file(fname)
        elif source == 'internet': self._init_from_internet()
        elif source == 'stdin': self._init_from_file('/dev/stdin')
        else: self._fail_hard('unknown source: {}. Failing'.format(source))
        self._prune_existing_results()

    def __iter__(self):
        return self._pairs.__iter__()

    def __len__(self):
        return len(self._pairs)

    def _init_from_file(self, fname):
        if not os.path.isfile(fname) and not os.path.islink(fname):
            self._fail_hard('{} doesn\'t exist. Failing.'.format(fname))
        self._log.notice('Initializing RelayList from {}'.format(fname))
        self._pairs = set()
        fname_ext = os.path.splitext(fname)[1]
        if fname_ext == '.xz': f = lzma.open(fname, 'rt')
        elif fname_ext in ['.gz','.gzip']: f = gzip.open(fname, 'rt')
        else: f = open(fname, 'rt')
        for line in f:
            #line = line[:-1] # trailing newline
            line = line.strip()
            if len(line) <= 0: continue # empty line
            if line[0] == '#': continue # comment
            fp1, fp2 = line.split(' ')
            assert len(fp1) == 40
            assert len(fp2) == 40
            if fp1 > fp2: fp1, fp2 = fp2, fp1
            self._pairs.add( (fp1, fp2) )
            if len(self._pairs) >= self._max_pairs: break
        f.close()
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
        #        if fp1 > fp2: fp1, fp2 = fp2, fp1
        #        self._pairs.add( (fp1, fp2) )
        #        if len(self._pairs) >= self._max_pairs: break
        #    if len(self._pairs) >= self._max_pairs: break
        ###
        # beter? method
        ###
        while len(self._pairs) < self._max_pairs:
            fp1, fp2 = random.sample(all_fps, 2)
            if fp1 > fp2: fp1, fp2 = fp2, fp1
            self._pairs.add( tuple(random.sample(all_fps, 2)) )
        self._log.notice('Finished reading {} relay pairs from the current '
                'consensus'.format(len(self._pairs)))
        if len(self._pairs) >= self._max_pairs:
            self._log.warn('We stopped adding relay pairs because we hit our '
                'configured maximimum')

    def _prune_existing_results(self):
        conf = self._conf
        log = self._log
        life = eval(conf['data']['result_life'])
        now = time.time()
        results_fname = os.path.join(conf['data']['result_dir'],
                conf['data']['result_file'])
        if not os.path.isfile(results_fname): return
        results = []
        for line in open(results_fname, 'rt'): results.append(json.loads(line))
        num_results = len(results)
        old_num_pairs = len(self._pairs)
        too_old_results = 0
        still_recent_results = 0
        for res in results:
            xy = ( res['x']['fp'], res['y']['fp'] )
            if xy[0] > xy[1]: xy = xy[1], xy[0]
            if res['time'] + life < now:
                too_old_results += 1
                continue
            else: still_recent_results += 1
            if xy in self._pairs:
                log.info('Removing {},{} from pairs because we have a recent '
                    'result.'.format(*[fp[0:8] for fp in xy]))
                self._pairs.remove(xy)
        new_num_pairs = len(self._pairs)
        log.notice('Trimmed {} pairs to {} using {} recent results '
            '({} were too old).'.format(old_num_pairs, new_num_pairs,
            still_recent_results, too_old_results))


    def _fail_hard(self, msg):
        self._log.error(msg)
        exit(1)
