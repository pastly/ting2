#!/usr/bin/env python3
from configparser import ConfigParser
from stem.control import Controller
from stem import SocketError
import ipaddress
conf = ConfigParser()
conf.read('config.ini')

def fail_hard(msg):
    print(msg)
    exit(1)

def notice(*args):
    #print(*args)
    pass

ctrl_port = conf.getint('torclient','ctrl_port')
cont = None
try:
    cont = Controller.from_port(port=ctrl_port)
except SocketError:
    fail_hard('SocketError: Couldn\'t connect to Tor control port {}'.format(
        ctrl_port))
if not cont:
    fail_hard('Couldn\'t connect to Tor control port {}'.format(ctrl_port))
if not cont.is_authenticated(): cont.authenticate()
if not cont.is_authenticated():
    fail_hard('Couldn\'t authenticate to Tor control port {}'.format(ctrl_port))

relays = [ r for r in cont.get_network_statuses() ]
notice('There are currently',len(relays),'relays in the entire Tor network')

#####
# Just do all relays
#####
all_relays = [ r.fingerprint for r in relays ]
all_relays.sort()
for i in range(0, len(all_relays)):
    [ print(all_relays[i], relay_j) for relay_j in all_relays[i+1:] ]
