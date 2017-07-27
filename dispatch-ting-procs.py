#!/usr/bin/env python3
import os
import shutil
import sys
import tempfile
import subprocess
import time
import json

def fail_hard(msg):
    print(msg)
    exit(1)

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

# https://stackoverflow.com/a/3041990
def query_yes_no(question, default="yes"):
    """Ask a yes/no question via input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None: prompt = " [y/n] "
    elif default == "yes": prompt = " [Y/n] "
    elif default == "no": prompt = " [y/N] "
    else: raise ValueError("invalid default answer: '%s'" % default)
    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '': return valid[default]
        elif choice in valid: return valid[choice]
        else: sys.stdout.write("Please respond with 'yes' or 'no' "
            "(or 'y' or 'n').\n")

def seconds_to_duration(secs):
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    d, h, m, s = int(d), int(h), int(m), int(round(s,0))
    if d > 0: return '{}d{}h{}m{}s'.format(d,h,m,s)
    elif h > 0: return '{}h{}m{}s'.format(h,m,s)
    elif m > 0: return '{}m{}s'.format(m,s)
    else: return '{}s'.format(s)

def combine_caches(cache_files):
    cache = {}
    in_items, out_items = 0, 0
    for fname in cache_files:
        tmp = json.load(open(fname, 'rt'))
        in_items += len(tmp)
        for k in tmp:
            if k not in cache: cache[k] = tmp[k]
            elif tmp[k]['rtt'] < cache[k]['rtt']: cache[k] = tmp[k]
    out_items = len(cache)
    for fname in cache_files: json.dump(cache, open(fname,'wt'))
    print('Deduped {} cache items down to {}.'.format(in_items, out_items))

template_dir = os.path.abspath('template')
num_procs = 4

ting_dirs = [ 'ting-proc-{}'.format(i) for i in range(0,num_procs) ]
for d in ting_dirs:
    if os.path.exists(d):
        if not query_yes_no('{} exists. Okay to delete?'.format(d), 'no'):
            fail_hard('Cannot continue')
        else: shutil.rmtree(d)
for ting_dir in ting_dirs: shutil.copytree(template_dir, ting_dir)

split_relay_list_dir = tempfile.mkdtemp()
#relay_list = os.path.abspath('2bignets-relaylist.txt')
relay_list = os.path.abspath('entirenetwork-relaylist.txt')
split_list_length = 100
subprocess.Popen(
    'split -l {} {}'.format(split_list_length, relay_list).split(),
    cwd=split_relay_list_dir).wait()
relay_lists = [ os.path.join(split_relay_list_dir, l) for l in \
    os.listdir(split_relay_list_dir) ]

num_runs = 0
total_run_time = 0
batches = batch(relay_lists, num_procs)
for bat in batches:
    relay_lists = bat
    procs = []
    print('Starting {} more ting procs'.format(len(relay_lists)))
    start_time = time.time()
    for i in range(0, len(relay_lists)):
        procs.append(subprocess.Popen(
            './ting2.py --ctrl-port {} --socks-port {}'.format(
                8720+i, 8730+i).split(' '),
            stdin=open(relay_lists[i], 'rt'),
            cwd=ting_dirs[i]))
    for proc in procs: proc.wait()
    end_time = time.time()
    duration = end_time - start_time
    total_run_time += duration
    num_runs += 1
    print('Run #{} took {}. Average run time {}. Total time {}.'.format(
        num_runs,
        seconds_to_duration(duration),
        seconds_to_duration(total_run_time / num_runs),
        seconds_to_duration(total_run_time)))
    combine_caches(['{}/results/cache.json'.format(td) for td in ting_dirs])

shutil.rmtree(split_relay_list_dir)
