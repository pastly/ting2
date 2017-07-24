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

######
# Beginning of trying to limit to one relay per subnet
######
#prefix_length = 24
#relay_nets = {}
#for relay in relays:
#    relay_ip = relay.address
#    relay_network = str(ipaddress.ip_network( (relay_ip, prefix_length),
#        strict=False))
#    if relay_network not in relay_nets:
#        relay_nets[relay_network] = []
#    relay_nets[relay_network].append(relay)
#notice('There are currently {} unique /{} networks'.format(
#    len(relay_nets), prefix_length))
#
#largest_net_size = 0
#largest_nets = [ ('', []) ]
#for net in relay_nets:
#    if len(relay_nets[net]) > largest_net_size:
#        largest_net_size = len(relay_nets[net])
#        largest_nets = [ (net, relay_nets[net]) ]
#    elif len(relay_nets[net]) == largest_net_size:
#        largest_nets.append( (net, relay_nets[net]) )
#notice('The largest networks contain {} relays and are \n    {}'.format(
#    largest_net_size, '\n    '.join([ n[0] for n in largest_nets])))
##notice('The largest network is {} and contains {} relays'.format(
##    largest_net[0], len(largest_net[1])))
#
#all_relays = [ relay for net in largest_nets for relay in net[1] ]
#all_relays = [ r.fingerprint for r in all_relays ]
#for a in all_relays:
#    for b in all_relays:
#        if a == b: continue
#        print(a,b)
