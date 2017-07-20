#!/usr/bin/env python3
import sys
from stem.control import Controller

port = int(sys.argv[1]) if len(sys.argv) > 1 else 9051

with Controller.from_port(port=port) as cont:
	cont.authenticate()
	all_circs = []
	for circ in cont.get_circuits():
		relays=[]
		for fp, nick in circ.path: relays.append(nick)
		all_circs.append( (circ.id, ' '.join(relays)) )
		#print circ.id, ' '.join(relays)
	used_circs = set()
	for s in cont.get_streams():
		used_circs.add(s.circ_id)
		#print s.circ_id, s.status, s.target_address
	for c_id in used_circs:
		try: circ = cont.get_circuit(c_id)
		except: continue
		relays=[]
		for fp, nick in circ.path: relays.append(nick)
		#print circ.id, ' '.join(relays)
	final = []
	all_circs.sort()
	for cid, path in all_circs:
		final.append('{} {} {}'.format(
			'*' if cid in used_circs else ' ',
			cid,
			path))
	for f in final:
		print(f)
	print(len(used_circs))
