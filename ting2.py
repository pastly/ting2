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
    return ting_client.tmp_test(*relays)

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
        rtts = pool.map(worker, [ (i,conf,log) for i in bat ])
        results.extend(rtts)
    pool.close()
    pool.join()
    for rtt in results:
        log.notice('Result: {} {} {}'.format(
                round(rtt[0]*1000,2) if rtt[0] != None else 'None',
                rtt[1][0:8], rtt[2][0:8]))
    #for s in conf.sections():
    #    print(conf.items(s))

if __name__ == '__main__':
    main()
