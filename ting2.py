#!/usr/bin/env python3
from configparser import ConfigParser
from pastlylogger import PastlyLogger
from tingclient import TingClient
from relaylist import RelayList
from multiprocessing.dummy import Pool as ThreadPool
from threading import Lock
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
    relays, conf, log = args
    ting_client = TingClient(conf, log,
            stream_creation_lock,
            (cache_dict, cache_dict_lock) )
    return ting_client.perform_on(*relays)

def main():
    global cache_dict
    log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
    #log = PastlyLogger(info='/dev/stdout', overwrite=['info'])
    conf = ConfigParser()
    conf.read('config.ini')
    relay_list = RelayList(conf, log)
    result_dname = os.path.abspath(conf['data']['result_dir'])
    cache_fname = os.path.join(result_dname, conf['data']['rtt_cache_file'])
    if not os.path.isfile(cache_fname):
        os.makedirs(result_dname)
        cache_dict = {}
        json.dump(cache_dict, open(cache_fname, 'wt'))
    cache_dict = json.load(open(cache_fname, 'rt'))
    results_fname = os.path.join(result_dname, conf['data']['result_file'])
    batches = [ b for b in \
            batch(relay_list, conf.getint('ting','concurrent_threads')) ]
    log.notice("Doing {} pairs of relays in {} batches".format(
        len(relay_list), len(batches)))
    results = []
    pool = ThreadPool(conf.getint('ting','concurrent_threads'))
    for bat in batches:
        res = pool.map(worker, [ (i,conf,log) for i in bat ])
        results.extend(res)
        cache_dict_lock.acquire()
        json.dump(cache_dict, open(cache_fname, 'wt'))
        cache_dict_lock.release()
        with open(results_fname, 'at') as f:
            for r in res:
                if r['rtt'] != None:
                    f.write('{}\n'.format(json.dumps(r)))
    pool.close()
    pool.join()
    for res in results:
        log.notice('Result: {} {} {}'.format(
            round(res['rtt']*1000,2) if res['rtt'] != None else 'None',
            res['x']['nick'], res['y']['nick']))
    #for s in conf.sections():
    #    print(conf.items(s))

if __name__ == '__main__':
    main()
