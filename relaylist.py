import os.path
class RelayList():
    def __init__(self, source, arg=None):
        fname = arg
        assert source == 'file' # only support this for now
        if not os.path.isfile(fname):
            print(fname, 'doesn\'t exist. Failing')
            exit(1)
        self._pairs = set()
        with open(fname, 'rt') as f:
            for line in f:
                #line = line[:-1] # trailing newline
                line = line.strip()
                if len(line) <= 0: continue # empty line
                if line[0] == '#': continue # comment
                fp1, fp2 = line.split(' ')
                assert len(fp1) == 40
                assert len(fp2) == 40
                self._pairs.add( (fp1, fp2) )

    def __iter__(self):
        return self._pairs.__iter__()

    def __len__(self):
        return len(self._pairs)
