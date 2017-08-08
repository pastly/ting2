#!/usr/bin/env python3
import json
import random
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType

def main(args):
    selected_relays = json.load(args.selected_relays)
    selected_relays = [ r['fp'] for r in selected_relays ]
    random.shuffle(selected_relays)
    pairs = []
    for i, fp1 in enumerate(selected_relays):
        for fp2 in selected_relays[i+1:]:
            if fp1 < fp2: pairs.append('{} {}\n'.format(fp1,fp2))
            else: pairs.append('{} {}\n'.format(fp2,fp1))
    args.outfile.write(''.join(pairs))

if __name__=='__main__':
    parser = ArgumentParser(
            formatter_class=ArgumentDefaultsHelpFormatter)
    DEF_SELECTED_RELAYS_FNAME = 'selected-relays.json'
    DEF_OUTFILE = 'reduced-relaypairs.txt'
    parser.add_argument('--selected-relays',
            help='Name of selected relays file',
            default=DEF_SELECTED_RELAYS_FNAME, type=FileType('rt'))
    parser.add_argument('--outfile',
            help='Where to dump relay pairs',
            default=DEF_OUTFILE, type=FileType('wt'))
    args = parser.parse_args()
    exit(main(args))
