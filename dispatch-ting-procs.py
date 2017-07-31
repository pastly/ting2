#!/usr/bin/env python3
import os
import shutil
import sys
import tempfile
import subprocess
import time
import json
from pastlylogger import PastlyLogger

log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
def fail_hard(*msg):
    if msg: log.error(*msg)
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
        if not os.path.exists(fname): continue
        tmp = json.load(open(fname, 'rt'))
        in_items += len(tmp)
        for k in tmp:
            if k not in cache: cache[k] = tmp[k]
            elif tmp[k]['rtt'] < cache[k]['rtt']: cache[k] = tmp[k]
    out_items = len(cache)
    for fname in cache_files: json.dump(cache, open(fname,'wt'))
    log.info('Deduped',in_items,'cache items down to',out_items)


template_dir = os.path.abspath('template')
num_procs = 4

ting_dirs = [ '/tmp/ting-proc-{}'.format(i) for i in range(0,num_procs) ]
for d in ting_dirs:
    if os.path.exists(d):
        if not query_yes_no('{} exists. Okay to delete?'.format(d), 'no'):
            fail_hard('Cannot continue')
        else: shutil.rmtree(d)
for ting_dir in ting_dirs: shutil.copytree(template_dir, ting_dir)

class TingProc:
    def __init__(self, ctrl_port, socks_port, cwd):
            self.ctrl_port = ctrl_port
            self.socks_port = socks_port
            self.cwd = cwd
            self.proc = None
            self.started_at = None
            self.num_relay_pairs = None
            self.haved_post_logged = False
    def is_running(self):
        if not self.proc: return False
        if self.proc.poll() == None: return True
        return False
    def wait(self):
        assert self.proc != None
        self.proc.wait()

global_cache = 'results/cache.json'
num_runs = 0
overall_start_time = 0
def cleanup_after_ting_proc(tp):
    global num_runs
    if tp.proc == None: return
    if tp.haved_post_logged: return
    duration = time.time() - tp.started_at
    overall_duration = time.time() - overall_start_time
    num_runs += 1
    log.notice('TingProc#{}'.format(tp.ctrl_port-8720),'took approx.',
        seconds_to_duration(duration),'measuring',tp.num_relay_pairs,
        'relay pairs.',num_runs,'runs have taken',
        seconds_to_duration(overall_duration))
    tp.haved_post_logged = True
    combine_caches([global_cache, '{}/results/cache.json'.format(tp.cwd)])

ting_procs = [ TingProc(8720+i, 8730+i, '/tmp/ting-proc-{}'.format(i)) \
        for i in range(0,num_procs) ]
def get_next_ting_proc():
    while True:
        for tp in ting_procs:
            if not tp.is_running():
                cleanup_after_ting_proc(tp)
                return tp
        time.sleep(1)

split_relay_list_dir = tempfile.mkdtemp()
relay_list = os.path.abspath('entirenetwork-relaylist.txt')
#relay_list = os.path.abspath('relaylist.txt')
split_list_length = 100
subprocess.Popen(
    'split -l {} {}'.format(split_list_length, relay_list).split(),
    cwd=split_relay_list_dir).wait()
relay_lists = [ os.path.join(split_relay_list_dir, l) for l in \
    os.listdir(split_relay_list_dir) ]

overall_start_time = time.time()
for relay_list in relay_lists:
    tp = get_next_ting_proc()
    tp.started_at = time.time()
    tp.num_relay_pairs = len([ l for l in open(relay_list, 'rt') ])
    tp.haved_post_logged = False
    tp.proc = subprocess.Popen(
            './ting2.py --ctrl-port {} --socks-port {}'.format(
                tp.ctrl_port, tp.socks_port).split(' '),
            stdin=open(relay_list, 'rt'),
            cwd=tp.cwd)
for tp in ting_procs:
    if tp.is_running(): tp.wait()
    cleanup_after_ting_proc(tp)

shutil.rmtree(split_relay_list_dir)
