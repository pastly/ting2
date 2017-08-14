#!/usr/bin/env python3
# Take a file with groups of relays
# Run ting on a sample of relays in each group
# Select a representative relay for each group
# Generate a list of relay pairs for ting using only the representative relays
import time
import json
import random
import subprocess
import os, shutil, os.path
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
from statistics import mean
# in virtualenv
# mine
from pastlylogger import PastlyLogger

log = PastlyLogger(info='/dev/stdout', overwrite=['info'])
def fail_hard(*msg):
    if msg: log.error(*msg)
    exit(1)

def seconds_to_duration(secs):
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    d, h, m, s = int(d), int(h), int(m), int(round(s,0))
    if d > 0: return '{}d{}h{}m{}s'.format(d,h,m,s)
    elif h > 0: return '{}h{}m{}s'.format(h,m,s)
    elif m > 0: return '{}m{}s'.format(m,s)
    else: return '{}s'.format(s)

def query_yes_no(question, default="yes"):
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None: prompt = " [y/n] "
    elif default == "yes": prompt = " [Y/n] "
    elif default == "no": prompt = " [y/N] "
    else: raise ValueError("invalid default answer: '%s'" % default)
    while True:
        print(question + prompt, end='')
        choice = input().lower()
        if default is not None and choice == '': return valid[default]
        elif choice in valid: return valid[choice]
        else: print("Please respond with 'yes' or 'no' "
            "(or 'y' or 'n').")

class TingProc:
    def __init__(self, ctrl_port, socks_port, cwd):
            self.ctrl_port = ctrl_port
            self.socks_port = socks_port
            self.cwd = cwd
            self.proc = None
    def is_running(self):
        if not self.proc: return False
        if self.proc.poll() == None: return True
        return False
    def wait(self):
        assert self.proc != None
        self.proc.wait()

def trim_too_small_groups(groups, size):
    log.notice('For groups smaller than',size,'we will just use all the '
            'relays')
    relays_to_use = []
    new_groups = {}
    for g in groups:
        group = groups[g]
        if len(group) < size: relays_to_use.extend(group)
        else: new_groups[g] = group
    return relays_to_use, new_groups

def create_ting_datadir(datadir):
    if os.path.exists(datadir):
        assert os.path.isdir(datadir)
        shutil.rmtree(datadir)
    fnames = ['ting2.py', 'pastlylogger.py', 'tingclient.py','relaylist.py',
            'config.ini']
    os.mkdir(datadir)
    os.mkdir(os.path.join(datadir, 'results'))
    for fname in fnames: shutil.copy2(fname, datadir)

def ting_within_group(group, args, sample_size, attempt_num='?'):
    ting = TingProc(args.ctrl, args.socks, args.datadir)
    sample = random.sample(group, sample_size)
    sample = [ r['fp'] for r in sample ]
    log.notice('(',attempt_num,'/',args.attempts,') Group of size',
            len(group),'trying reps:',', '.join([ s[0:8] for s in sample]))
    pairs = set()
    input_data = ''
    for i, fp1 in enumerate(sample):
        for fp2 in sample[i+1:]:
            if fp1 > fp2: pairs.add( (fp2, fp1) )
            else: pairs.add( (fp1, fp2) )
    for pair in pairs: input_data += '{} {}\n'.format(*pair)
    #print(input_data)
    ting.proc = subprocess.Popen(
            './ting2.py --ctrl-port {} --socks-port {}'.format(
                ting.ctrl_port, ting.socks_port).split(' '),
            stdin=subprocess.PIPE,
            cwd=ting.cwd)
    ting.proc.communicate(bytes(input_data, 'utf-8'))
    ting.wait()
    results_fname = os.path.join(ting.cwd,'results','results.json')
    if not os.path.exists(results_fname): return []
    assert os.path.isfile(results_fname)
    results = []
    for line in open(results_fname, 'rt'):
        results.append(json.loads(line))
    return results

def best_relay_from_results(results, required_len, max_allowed_rtt):
    relays = {}
    log.info('Choosing best representative relay using',len(results),'results')
    for result in results:
        rtt = max(0, result['rtt'])
        fp = result['x']['fp']
        if fp not in relays: relays[fp] = []
        relays[fp].append(rtt)
        fp = result['y']['fp']
        if fp not in relays: relays[fp] = []
        relays[fp].append(rtt)
    #for k, v in list(relays.items()):
    #    if not len(v) >= required_len:
    #        log.info('Removing',k[0:8],'because',len(v),'is less than the '
    #                'required',required_len,'results')
    #        del relays[k]
    #    elif max(v)*1000 >= max_allowed_rtt:
    #        log.info('Removing',k[0:8],'because it has 1+ RTT greater than',
    #                max_allowed_rtt)
    #        del relays[k]
    for k, v in list(relays.items()):
        if mean(v)*1000 >= max_allowed_rtt:
            log.info('Removing',k[0:8],'because it has a mean RTT greater than',
                    max_allowed_rtt,[ round(1000*vi,2) for vi in v ])
            del relays[k]
    best_relay = None
    log.info(len(relays),'remaining candidate relays')
    for r in relays:
        if not best_relay or mean(relays[r]) < best_relay[1]:
            best_relay = ( r, mean(relays[r]) )
    if not best_relay:
        log.info('There was no remaining best relay')
        return None
    log.info(best_relay[0][0:8],'was the best with an rtt mean of',
            round(best_relay[1]*1000, 2),'ms ',
            [ round(1000*rtt,2) for rtt in relays[best_relay[0]] ])
    return best_relay[0]

def get_representative_relay(group, args):
    relay = None
    for max_allowed_rtt in args.max_allowed_rtt:
        log.notice('Requiring a max mean RTT of',max_allowed_rtt,'ms')
        for attempt_num in range(args.attempts):
            create_ting_datadir(args.datadir)
            sample_size = min(args.max_group_size, len(group))
            results = ting_within_group(group, args, sample_size,
                    attempt_num=attempt_num+1)
            relay_fp = best_relay_from_results(results, sample_size-1,
                    max_allowed_rtt)
            if not relay_fp: continue
            for r in group:
                if r['fp'] == relay_fp:
                    relay = r
                    break
            if relay: break
        if relay: break
    if not relay:
        log.warn('Tried',len(args.max_allowed_rtt)*args.attempts,'times to get '
                'a representative relay, but couldn\'t. Returning all the '
                'relays in the group.')
        return group
    return [relay]

def main(args):
    groups = json.load(args.groups)
    relays_to_use = []
    if args.non_group in groups:
        log.notice(len(groups[args.non_group]),'relays without a group')
        relays_to_use.extend(groups[args.non_group])
        del groups[args.non_group]
    log.notice('Read',len(groups),'groups from file')
    rtu, groups = trim_too_small_groups(groups, args.min_group_size)
    relays_to_use.extend(rtu)
    log.notice('After trimming small groups, there are',len(groups),'remaining '
            'groups.', len(relays_to_use),'relays will have to represent '
            'themselves.')
    if os.path.exists(args.datadir):
        if not query_yes_no('{} exists and will be deleted. That ok?'.format(
            args.datadir)):
            fail_hard('Then we cannot continue')
        if os.path.isdir(args.datadir): shutil.rmtree(args.datadir)
        elif os.path.isfile(args.datadir): os.remove(args.datadir)
        else: fail_hard('Don\'t know what {} is so cannot delete')
    total_time = 0
    for i, g in enumerate(groups):
        log.notice('Now serving group',i+1,'of',len(groups))
        group = groups[g]
        start = time.time()
        rtu = get_representative_relay(group, args)
        end = time.time()
        total_time += end-start
        log.notice('Group',i+1,'of',len(groups),'took',
                seconds_to_duration(end-start),'Will be done in ~',
                seconds_to_duration(total_time/(i+1)*(len(groups)-i-1)))
        relays_to_use.extend(rtu)
        if args.outfile.seekable(): args.outfile.seek(0)
        json.dump(relays_to_use, args.outfile)
    log.notice('Ready to ting between the',len(relays_to_use),'representative '
            'relays.')

if __name__=='__main__':
    parser = ArgumentParser(
            formatter_class=ArgumentDefaultsHelpFormatter)
    DEF_RELAYS_FILE = 'relay-groups.json'
    DEF_OUTPUT_FILE = 'selected-relays.json'
    DEF_NON_GROUP = "-1" # yes ... it has to be a string.
    DEF_MIN_GROUP_SIZE = 3
    DEF_MAX_GROUP_SIZE = 10
    DEF_MAX_ALLOWED_RTT = [10,20]
    DEF_ATTEMPTS = 3
    DEF_CTRL_PORT = 8720
    DEF_SOCKS_PORT = 8730
    DEF_DATADIR = os.path.abspath('/tmp/tmpting')
    parser.add_argument('-g','--groups',
            help='Input file with relays split into groups',
            default=DEF_RELAYS_FILE, type=FileType('rt'))
    parser.add_argument('-o','--outfile',
            help='Output file to put representative relays into',
            default=DEF_OUTPUT_FILE, type=FileType('wt'))
    parser.add_argument('--non-group',
            help='Group ID for the group of relays without a group',
            default=DEF_NON_GROUP)
    parser.add_argument('-m','--min-group-size',
            help='Minimum group size needed to do ting and select a '
            'representative relay for the group',
            default=DEF_MIN_GROUP_SIZE, type=int)
    parser.add_argument('-M','--max-group-size',
            help='Maximum group size that will be sampled and tinged between',
            default=DEF_MAX_GROUP_SIZE, type=int)
    parser.add_argument('-a','--attempts',
            help='Maximum number of times to try to find a good representative '
            'relay before using all relays in a group',
            default=DEF_ATTEMPTS, type=int)
    parser.add_argument('-r','--max-allowed-rtt',
            help='Add an RTT to the list of maximum mean RTTs. If the average '
            'RTT from one relay to all other relays in a group is greater than '
            'this, then it will not be a candidate. Can be specified multiple '
            'times. Each RTT will be tried in increasing order.',
            default=DEF_MAX_ALLOWED_RTT, type=float, action='append')
    parser.add_argument('--ctrl', help='Tor control port',
        default=DEF_CTRL_PORT, type=int)
    parser.add_argument('--socks', help='Tor socks port',
        default=DEF_SOCKS_PORT, type=int)
    parser.add_argument('--datadir', help='Ting data dir to create',
            default=DEF_DATADIR, type=str)
    args = parser.parse_args()
    if args.max_allowed_rtt != DEF_MAX_ALLOWED_RTT:
        args.max_allowed_rtt = args.max_allowed_rtt[len(DEF_MAX_ALLOWED_RTT):]
    args.max_allowed_rtt.sort()
    exit(main(args))

