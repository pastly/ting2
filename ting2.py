#!/usr/bin/env python3
from configparser import ConfigParser
from pastlylogger import PastlyLogger
from tingclient import TingClient
from relaylist import RelayList
import time
from multiprocessing.dummy import Pool as ThreadPool

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
    ting_client = TingClient(conf, log)
    return ting_client.tmp_test(*relays)

def main():
    log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
    #log = PastlyLogger(info='/dev/stdout', overwrite=['info'])
    conf = ConfigParser()
    conf.read('config.ini')
    relay_list = RelayList('file', conf['ting']['relay_list'])
    ting_client = TingClient(conf, log)
    batches = [ b for b in \
            batch(relay_list, conf.getint('ting','concurrent_threads')) ]
    log.notice("Doing {} pairs of relays in {} batches".format(
        len(relay_list), len(batches)))
    results = []
    for bat in batches:
        num_threads = len(bat)
        pool = ThreadPool(num_threads)
        rtts = pool.map(worker, [ (i,conf,log) for i in bat ])
        pool.close()
        pool.join()
        results.extend(rtts)
    for rtt in results: print(round(rtt*1000,2))
    #for s in conf.sections():
    #    print(conf.items(s))

if __name__ == '__main__':
    main()
