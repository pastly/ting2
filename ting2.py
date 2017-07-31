#!/usr/bin/env python3
from configparser import ConfigParser
from pastlylogger import PastlyLogger
from tingclient import TingClient
from relaylist import RelayList
from multiprocessing.dummy import Pool as ThreadPool
from threading import Lock
import time
import os
import json
import argparse
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

def main():
    global cache_dict
    log = PastlyLogger(debug='results/debug.log', log_threads=True)
    #log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
    conf = ConfigParser()
    conf.read('config.ini')
    parser = argparse.ArgumentParser()
    parser.add_argument('--ctrl-port', metavar='PORT',
        help='Port on which to control Tor')
    parser.add_argument('--socks-port', metavar='PORT',
        help='Port on which to send traffic to Tor')
    args = parser.parse_args()
    if args.ctrl_port: conf['torclient']['ctrl_port'] = args.ctrl_port
    if args.socks_port: conf['torclient']['socks_port'] = args.socks_port
    relay_list = RelayList(conf, log)
    if len(relay_list) < 1:
        log.notice('There\'s nothing to do')
        exit(0)
    result_dname = os.path.abspath(conf['data']['result_dir'])
    cache_fname = os.path.join(result_dname, conf['data']['rtt_cache_file'])
    if not os.path.isfile(cache_fname):
        os.makedirs(result_dname, exist_ok=True)
        cache_dict = {}
        json.dump(cache_dict, open(cache_fname, 'wt'))
    cache_dict = json.load(open(cache_fname, 'rt'))
    results_fname = os.path.join(result_dname, conf['data']['result_file'])
    num_threads = conf.getint('ting','concurrent_threads')
    batches = [ b for b in batch(relay_list, num_threads) ]
    log.notice("Doing {} pairs of relays in {} batches".format(
        len(relay_list), len(batches)))
    results = []
    with ThreadPool(num_threads) as pool:
        ting_clients = [ TingClient(conf, log,
            stream_creation_lock, (cache_dict, cache_dict_lock) ) for _ in \
            range(0,num_threads) ]
        bat_num = 0
        for bat in batches:
            bat_num += 1
            start_time = time.time()
            #res = pool.map(worker, [ (i,conf,log) for i in bat ])
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
    #for s in conf.sections():
    #    print(conf.items(s))

if __name__ == '__main__':
    main()
