#!/usr/bin/env bash
# Helper script to start a number of Tor processes for ting2 to then use
DD=$(pwd)/tordatadirs
TOR_BIN="$HOME/src/tor/src/or/tor"
mkdir $DD
# SocksPorts will be whatever is listed in the for loop
# ControlPorts will be +1 of SocksPorts
for A in 12000 12002 12004 12006 12008 12010; do
    $TOR_BIN \
        --SocksPort $A \
        --ControlPort $(($A+1)) \
        --CookieAuthentication 1 \
        --Log "err file $DD/$A/error.log" \
        --DataDirectory $DD/$A \
        --PidFile $DD/$A/tor.pid \
        --defaults-torrc /dev/null \
        --LearnCircuitBuildTimeout 0 \
        --CircuitBuildTimeout 10 \
        --RunAsDaemon 1 \
        --Bridge "216.218.222.14:9003 B28D5058E30620358B33D75BFB9F20192CF82270" \
        --UseBridges 1 \
        ;
done
