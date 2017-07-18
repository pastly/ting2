#!/usr/bin/env python3
from configparser import ConfigParser
from pastlylogger import PastlyLogger
from tingclient import TingClient
import time
def main():
    #log = PastlyLogger(debug='/dev/stdout', overwrite=['debug'])
    log = PastlyLogger(info='/dev/stdout', overwrite=['info'])
    conf = ConfigParser()
    conf.read('ting.config.ini')
    ting_client = TingClient(conf, log)
    while True:
        ting_client.tmp_test()
        break
        time.sleep(3)
    #for s in conf.sections():
    #    print(conf.items(s))

if __name__ == '__main__':
    main()
