#!/usr/bin/env python3
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
import os
import shutil
import sys
import tempfile
import subprocess
import time
import json
from pastlylogger import PastlyLogger

log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
log = PastlyLogger(notice='/dev/stdout', overwrite=['notice'])
def fail_hard(*msg):
    if msg: log.error(*msg)
    exit(1)

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

def make_ting_dirs(args):
    ting_dirs = [ '{}/ting-proc-{}'.format(args.tmpdir,i) \
            for i in range(0,len(args.socks_port)) ]
    for d in ting_dirs:
        if os.path.exists(d):
            if not query_yes_no('{} exists. Okay to delete?'.format(d), 'no'):
                fail_hard('Cannot continue')
            shutil.rmtree(d)
        os.mkdir(d)
        os.mkdir(os.path.join(d,'data'))
    files = [ f for f in os.listdir() if f[-3:] == '.py' ]
    for ting_dir in ting_dirs:
        for f in files: shutil.copy2(f, ting_dir)
    return ting_dirs

def get_relaylist_files(args):
    relaylist_files = []
    all_files = os.listdir(args.relaylist_dir)
    all_files.sort()
    for fname in all_files:
        fname = os.path.join(args.relaylist_dir, fname)
        root, ext = os.path.splitext(fname)
        if root in relaylist_files and ext == '.done':
            relaylist_files.remove(root)
        else:
            relaylist_files.append(fname)
    return relaylist_files

class TingProc:
    def __init__(self, ctrl_port, socks_port, cwd):
            self.ctrl_port = ctrl_port
            self.socks_port = socks_port
            self.cwd = cwd
            self.proc = None
            self.cleaned_up = False
            self.relay_pairs_fname = None
    def is_running(self):
        if not self.proc: return False
        if self.proc.poll() == None: return True
        return False
    def wait(self):
        assert self.proc != None
        self.proc.wait()

def combine_caches(*cache_files):
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

def combine_results(main_fname, sub_fname):
    if not os.path.exists(sub_fname): return
    with open(main_fname, 'at') as out_file:
        for line in open(sub_fname, 'rt'):
            line = line.strip()
            if len(line) <= 0: continue
            if line[0] == '#': continue
            out_file.write('{}\n'.format(line))

def cleanup_after_ting_proc(args, tp):
    if tp.proc == None: return
    if tp.cleaned_up: return
    tp.cleaned_up = True
    global_cache = args.out_cache_file
    tp_cache = os.path.join(tp.cwd,'data','cache.json')
    combine_caches(global_cache,tp_cache)
    global_results = args.out_result_file
    tp_results = os.path.join(tp.cwd,'data','results.json')
    combine_results(global_results, tp_results)
    if os.path.exists(tp_results):
        os.remove(tp_results)
    open(tp.relay_pairs_fname+'.done', 'at') # touch

def get_next_ting_proc(args, ting_procs):
    while True:
        for tp in ting_procs:
            if not tp.is_running():
                cleanup_after_ting_proc(args, tp)
                return tp
        time.sleep(1)

def main(args):
    log.notice('Called as:',*sys.argv)
    ting_dirs = make_ting_dirs(args)
    relaylist_files = get_relaylist_files(args)
    ting_procs = [ TingProc(args.ctrl_port[i], args.socks_port[i],
        ting_dirs[i]) for i in range(0, len(args.socks_port)) ]
    log.notice('Will use',len(ting_procs),'ting procs to process',
            len(relaylist_files),'realylist files')
    start = time.time()
    last_stat_at = start
    for i, rl in enumerate(relaylist_files):
        tp = get_next_ting_proc(args, ting_procs)
        tp.cleaned_up = False
        tp.relay_pairs_fname = rl
        tp.proc = subprocess.Popen(
            './ting2.py --ctrl-port {} --socks-port {} '\
            '--w-relay {} --z-relay {} --samples {} '\
            '--target-host {} --target-port {} '\
            '--threads {} --relay-source stdin --cache-3hop '\
            .format(tp.ctrl_port, tp.socks_port,
            args.w_relay, args.z_relay, args.samples,
            args.target_host, args.target_port,
            args.threads).strip().split(' '),
            stdin=open(rl, 'rt'), cwd=tp.cwd)
        now = time.time()
        if last_stat_at + args.stats_interval <= now:
            dur = seconds_to_duration(now - start)
            rem = ((now - start) * len(relaylist_files) / i) - (now - start)
            rem = seconds_to_duration(rem)
            log.notice('We are on item {}/{} ({}% done)'.format(i,
                len(relaylist_files), round(i*100.0/len(relaylist_files),1)),
                'It has taken',dur,'and we expect to be done in',rem)
            last_stat_at = now
    for tp in ting_procs:
        if tp.is_running():
            tp.wait()
        cleanup_after_ting_proc(args, tp)

if __name__=='__main__':
    parser = ArgumentParser(
            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--tmpdir', metavar='DIR', type=str,
            help='Directory in which to put temporary ting data dirs',
            default='/tmp')
    parser.add_argument('--relaylist-dir', metavar='DIR', type=str,
            help='Directory containing a bunch of relaylist files. We will '
            'feed them to ting processes one at a time.',
            required=True)
    parser.add_argument('--socks-port', metavar='PORT', type=int,
            help='Add a port to the list of socks ports. The number of socks '
            'ports determines the number of ting2.py processes to run.',
            required=True, action='append')
    parser.add_argument('--ctrl-port', metavar='PORT', type=int,
            help='Add a port to the list of control ports. They correspond '
            'to the socks ports in the order they are specified. The number '
            'of ctrl and socks ports must be equal.',
            required=True, action='append')
    parser.add_argument('--threads', metavar='NUM', type=int,
            help='Number of threads a ting process should run in parallel',
            default=16)
    parser.add_argument('--w-relay', metavar='FP', type=str, required=True,
            help='Fingerprint of the relay to use in the W position')
    parser.add_argument('--z-relay', metavar='FP', type=str, required=True,
            help='Fingerprint of the relay to use in the Z position')
    parser.add_argument('--samples', metavar='NUM', type=int,
            help='How many "tings" to send over a completed circuit and take '
            'the min() of and call the RTT', default=200)
    parser.add_argument('--target-host', metavar='HOST', type=str,
            help='Host/IP that the echo server is running', required=True)
    parser.add_argument('--target-port', metavar='PORT', type=int,
            help='Port on which the echo server is running', default=16667)
    parser.add_argument('--out-cache-file', metavar='FNAME',
            help='Name of file to store cached data in',
            type=str, default='data/cache.json')
    parser.add_argument('--out-result-file', metavar='FNAME',
            help='Name of file to which to write results',
            type=str, default='data/results.json')
    parser.add_argument('--stats-interval', metavar='SECS', type=float,
            help='Log information about our progress every SECS seconds at '
            'level "notice"', default=60)
    args = parser.parse_args()
    assert len(args.ctrl_port) == len(args.socks_port)
    assert len(args.w_relay) == 40
    assert len(args.z_relay) == 40
    assert os.path.exists(args.relaylist_dir) and \
            os.path.isdir(args.relaylist_dir)
    exit(main(args))
