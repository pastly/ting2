#!/usr/bin/env python3
from configparser import ConfigParser
from pastlylogger import PastlyLogger
from tingclient import TingClient
from relaylist import RelayList
from multiprocessing.dummy import Pool as ThreadPool
from threading import Lock
stream_creation_lock = Lock()

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
    ting_client = TingClient(conf, log, stream_creation_lock)
    return ting_client.perform_on(*relays)

def main():
    log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
    #log = PastlyLogger(info='/dev/stdout', overwrite=['info'])
    conf = ConfigParser()
    conf.read('config.ini')
    relay_list = RelayList(conf, log)
    batches = [ b for b in \
            batch(relay_list, conf.getint('ting','concurrent_threads')) ]
    log.notice("Doing {} pairs of relays in {} batches".format(
        len(relay_list), len(batches)))
    results = []
    pool = ThreadPool(conf.getint('ting','concurrent_threads'))
    for bat in batches:
        res = pool.map(worker, [ (i,conf,log) for i in bat ])
        results.extend(res)
    pool.close()
    pool.join()
    for res in results:
        log.notice('Result: {} {} {}'.format(
            round(res['rtt']*1000,2) if res['rtt'] != None else 'None',
            res['x'][0:8], res['y'][0:8]))
    #for s in conf.sections():
    #    print(conf.items(s))

if __name__ == '__main__':
    main()
