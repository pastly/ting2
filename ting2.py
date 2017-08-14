#!/usr/bin/env python3
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
from pastlylogger import PastlyLogger
from tingclient import TingClient
from relaylist import RelayList
from resultsmanager import ResultsManager
from threading import Event, Lock, Thread
from queue import Empty, Queue
import json, os, sys, time

log = PastlyLogger(notice='data/notice.log', log_threads=True)
#log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'], log_threads=True)

def seconds_to_duration(secs):
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    d, h, m, s = int(d), int(h), int(m), int(round(s,0))
    if d > 0: return '{}d{}h{}m{}s'.format(d,h,m,s)
    elif h > 0: return '{}h{}m{}s'.format(h,m,s)
    elif m > 0: return '{}m{}s'.format(m,s)
    else: return '{}s'.format(s)

class ClientThread():
    def __init__(self, args, log, stream_creation_lock, cache_dict,
            results_manager, is_shutting_down, name):
        self._is_shutting_down = is_shutting_down
        self._stream_creation_lock = stream_creation_lock
        self.cache_dict = cache_dict
        self._results_manager = results_manager
        self._args = args
        self._log = log
        self.input = Queue(maxsize=1)
        self.thread = Thread(target=self._enter)
        self.thread.name = name
        self.name = self.thread.name
        self.thread.start()

    def wait(self):
        assert self.thread != None
        self.thread.join()

    def _enter(self):
        self._client = TingClient(self._args, self._log,
                self._stream_creation_lock, self.cache_dict,
                self._results_manager)
        while True:
            fp1, fp2 = None, None
            try: fp1, fp2 = self.input.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set(): break
                self._log.debug('No pending work')
                continue
            if fp1 and fp2:
                self._client.perform_on(fp1,fp2)

cleanup_count = 0
def cleanup_after_ting_thread(args, thr, force=False):
    global cleanup_count
    cleanup_count += 1
    if force or cleanup_count >= args.write_cache_every:
        if not force: cleanup_count -= args.write_cache_every
        cache_dict, cache_dict_lock = thr.cache_dict
        cache_fname = args.out_cache_file
        with cache_dict_lock:
            log.info('Writing',len(cache_dict),'cached items to cache file')
            json.dump(cache_dict, open(cache_fname, 'wt'))

def get_next_client_thread(args, threads):
    while True:
        for thr in threads:
            if not thr.input.full():
                cleanup_after_ting_thread(args, thr)
                return thr
        time.sleep(0.5)

def dispatch_client_thread(thr, fp1, fp2):
    log.info('Giving',thr.name,fp1,fp2)
    thr.input.put( (fp1, fp2) )

def main(args):
    log.notice('Called as:',*sys.argv)
    kill_client_threads = Event()
    kill_results_thread = Event()
    stream_creation_lock = Lock()
    cache_dict_lock = Lock()
    cache_dict = None
    relay_list = RelayList(args, log)
    if len(relay_list) < 1:
        log.notice('There\'s nothing to do')
        exit(0)
    rm = ResultsManager(args, log, kill_results_thread)
    cache_fname = os.path.abspath(args.out_cache_file)
    if not os.path.isfile(cache_fname):
        os.makedirs(os.path.dirname(cache_fname), exist_ok=True)
        cache_dict = {}
        json.dump(cache_dict, open(cache_fname, 'wt'))
    cache_dict = json.load(open(cache_fname, 'rt'))
    client_threads = [ ClientThread(args, log, stream_creation_lock,
        (cache_dict, cache_dict_lock), rm, kill_client_threads,
        'worker-{}'.format(i)) \
        for i in range(0, args.threads) ]
    start = time.time()
    last_stat_at = start
    for i, item in enumerate(relay_list):
        fp1, fp2 = item
        dispatch_client_thread(get_next_client_thread(args, client_threads),
            fp1, fp2)
        now = time.time()
        if last_stat_at + args.stats_interval <= now:
            dur = seconds_to_duration(now - start)
            rem = ((now - start) * len(relay_list) / i) - (now - start)
            rem = seconds_to_duration(rem)
            log.notice('We are on item {}/{} ({}% done)'.format(i,
                len(relay_list), round(i*100.0/len(relay_list),1)),'It has '
                'taken',dur,'and we expect to be done in',rem)
            last_stat_at = now
    kill_client_threads.set()
    for thr in [ t for t in client_threads if t.thread ]:
        thr.wait()
    cleanup_after_ting_thread(args, client_threads[0], force=True)
    kill_results_thread.set()

if __name__ == '__main__':
    parser = ArgumentParser(
            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--ctrl-port', metavar='PORT', type=int,
            help='Port on which to control the tor client', default=9051)
    parser.add_argument('--socks-host', metavar='HOST', type=str,
            help='Host/IP to send traffic to the tor client',
            default='127.0.0.1')
    parser.add_argument('--socks-port', metavar='PORT', type=int,
            help='Port on which to send traffic to the tor client',
            default=9050)
    parser.add_argument('--w-relay', metavar='FP', type=str, required=True,
            help='Fingerprint of the relay to use in the W position')
    parser.add_argument('--z-relay', metavar='FP', type=str, required=True,
            help='Fingerprint of the relay to use in the Z position')
    parser.add_argument('--circ-build-attempts', metavar='NUM', type=int,
            help='Number of times we should try to build a circuit before '
            'starting a measurement', default=3)
    parser.add_argument('--measurement-attempts', metavar='NUM', type=int,
            help='Number of times we should try to collect all the samples '
            'over a completed circuit', default=3)
    parser.add_argument('--socks-timeout', metavar='SECS', type=int,
            help='How long to wait for a socket to connect()',
            default=10)
    parser.add_argument('--samples', metavar='NUM', type=int,
            help='How many "tings" to send over a completed circuit and take '
            'the min() of and call the RTT', default=200)
    parser.add_argument('--target-host', metavar='HOST', type=str,
            help='Host/IP that the echo server is running', required=True)
    parser.add_argument('--target-port', metavar='PORT', type=int,
            help='Port on which the echo server is running', default=16667)
    parser.add_argument('--threads', metavar='NUM', type=int,
            help='Number of threads, and thus measurements, to use at once',
            default=1)
    parser.add_argument('--relay-source', metavar='SRC', type=str,
            help='Where to get relays to ting between',
            choices=['internet','file','stdin'], default='internet')
    parser.add_argument('--relay-source-file', metavar='FNAME',
            help='If SRC is file, the name of the file to read',
            type=FileType('rt'), default='/dev/null')
    parser.add_argument('--relay-max-pairs', metavar='NUM', type=int,
            help='Maximum number of relay pairs to read from SRC',
            default=100)
    parser.add_argument('--out-cache-file', metavar='FNAME',
            help='Name of file to store cached data in',
            type=str, default='data/cache.json')
    parser.add_argument('--out-result-file', metavar='FNAME',
            help='Name of file to which to write results',
            type=str, default='data/results.json')
    parser.add_argument('--write-results-every', metavar='NUM',
            help='Write results to file every time we collect NUM results',
            default=10)
    parser.add_argument('--cache-4hop', action='store_true',
            help='Whether or not to cache 4hop results in the cache file')
    parser.add_argument('--cache-4hop-life', metavar='SECS', type=int,
            help='How long to consider 4hop cached results fresh',
            default=60*60*24*1)
    parser.add_argument('--cache-3hop', action='store_true',
            help='Whether or not to cache 3hop results in the cache file')
    parser.add_argument('--cache-3hop-life', metavar='SECS', type=int,
            help='How long to consider 3hop cached results fresh',
            default=60*60*24*1)
    parser.add_argument('--write-cache-every', metavar='NUM',
            help='Write cache file after every NUM collected results',
            default=10)
    parser.add_argument('--result-life', metavar='SECS', type=int,
            help='When starting up and reading relay pairs from a source, we '
            'ignore a pair if we have a recent enough result already',
            default=60*60*24*100)
    parser.add_argument('--stats-interval', metavar='SECS', type=float,
            help='Log information about our progress every SECS seconds at '
            'level "notice"', default=60)
    args = parser.parse_args()
    assert len(args.w_relay) == 40
    assert len(args.z_relay) == 40
    exit(main(args))
