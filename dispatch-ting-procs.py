#!/usr/bin/env python3
import os
import shutil
import sys
import tempfile
import subprocess
import time

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
relay_list = os.path.abspath('2bignets-relaylist.txt')
split_list_length = 100
subprocess.Popen(
    'split -l {} {}'.format(split_list_length, relay_list).split(),
    cwd=split_relay_list_dir).wait()
relay_lists = [ os.path.join(split_relay_list_dir, l) for l in \
    os.listdir(split_relay_list_dir) ]

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
    print('That took {} seconds'.format(duration))

shutil.rmtree(split_relay_list_dir)
