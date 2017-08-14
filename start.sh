#!/usr/bin/env bash
./dispatch-ting-procs.py \
--samples 20 \
--socks-port 12000 ctrl-port 12001 \
--socks-port 12002 ctrl-port 12003 \
--socks-port 12004 ctrl-port 12005 \
--socks-port 12006 ctrl-port 12007 \
--socks-port 12008 ctrl-port 12009 \
--socks-port 12010 ctrl-port 12011 \
--w-relay B28D5058E30620358B33D75BFB9F20192CF82270 \
--z-relay 16ED9CBEA6671C020F598D64A30EA996DFE370FF \
--target-host 216.218.222.14 \
--relaylist-dir reduced-relaypairs-split
