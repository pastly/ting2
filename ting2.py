#!/usr/bin/env python3
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
from pastlylogger import PastlyLogger
from tingclient import TingClient
from relaylist import RelayList
from multiprocessing.dummy import Pool as ThreadPool
from threading import Lock
import time
import os
import json
stream_creation_lock = Lock()
cache_dict_lock = Lock()
cache_dict = None

# https://stackoverflow.com/q/8290397
def batch(iterable, n = 1):
   current_batch = []
   for item in iterable:
       current_batch.append(item)
       if len(current_batch) == n:
           yield current_batch
           current_batch = []
   if current_batch:
       yield current_batch

def worker(args):
    ting_client, relays = args
    return ting_client.perform_on(*relays)

def seconds_to_duration(secs):
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    d, h, m, s = int(d), int(h), int(m), int(round(s,0))
    if d > 0: return '{}d{}h{}m{}s'.format(d,h,m,s)
    elif h > 0: return '{}h{}m{}s'.format(h,m,s)
    elif m > 0: return '{}m{}s'.format(m,s)
    else: return '{}s'.format(s)

def main(args):
    global cache_dict
    #log = PastlyLogger(debug='data/debug.log', log_threads=True)
    log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
    relay_list = RelayList(args, log)
    if len(relay_list) < 1:
        log.notice('There\'s nothing to do')
        exit(0)
    cache_fname = os.path.abspath(args.out_cache_file)
    if not os.path.isfile(cache_fname):
        os.makedirs(os.path.dirname(cache_fname), exist_ok=True)
        cache_dict = {}
        json.dump(cache_dict, open(cache_fname, 'wt'))
    cache_dict = json.load(open(cache_fname, 'rt'))
    results_fname = os.path.abspath(args.out_result_file)
    num_threads = args.threads
    batches = [ b for b in batch(relay_list, num_threads) ]
    log.notice("Doing {} pairs of relays in {} batches".format(
        len(relay_list), len(batches)))
    results = []
    with ThreadPool(num_threads) as pool:
        ting_clients = [ TingClient(args, log,
            stream_creation_lock, (cache_dict, cache_dict_lock) ) for _ in \
            range(0,num_threads) ]
        bat_num = 0
        for bat in batches:
            bat_num += 1
            start_time = time.time()
            res = pool.map(worker, [ (ting_clients[i], bat[i]) for i in \
                range(0,len(bat)) ])
            end_time = time.time()
            duration = end_time - start_time
            results.extend(res)
            cache_dict_lock.acquire()
            json.dump(cache_dict, open(cache_fname, 'wt'))
            cache_dict_lock.release()
            valid_results = [ r for r in res if r['rtt'] != None ]
            with open(results_fname, 'at') as f:
                for r in valid_results: f.write('{}\n'.format(json.dumps(r)))
            log.notice('It took {} ({} sec per measurement) to process '
                'batch {}/{}. There were {} measurements, of which {} produced '
                'results.'.format(seconds_to_duration(duration),
                    round(duration/len(bat),2), bat_num, len(batches),
                    len(bat), len(valid_results)))
    for res in results:
        log.notice('Result: {} {} {}'.format(
            round(res['rtt']*1000,2) if res['rtt'] != None else 'None',
            res['x']['nick'], res['y']['nick']))

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
    parser.add_argument('--result-life', metavar='SECS', type=int,
            help='When starting up and reading relay pairs from a source, we '
            'ignore a pair if we have a recent enough result already',
            default=60*60*24*100)
    args = parser.parse_args()
    assert len(args.w_relay) == 40
    assert len(args.z_relay) == 40
    exit(main(args))
