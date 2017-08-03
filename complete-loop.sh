#!/usr/bin/env bash
RELAYLIST_DIR=results/entirenetwork
TEMP_DIR=/tmp
LOG_FILE=results/complete-loop.log
ALL_RESULTS=results/results.json
find $RELAYLIST_DIR -type f | \
    while read F; do
        echo $(date) Doing $F | tee -a $LOG_FILE
        ./dispatch-ting-procs.py $F
        echo $(date) Moving results in $TEMP_DIR/ting-proc-* $ALL_RESULTS | tee -a $LOG_FILE
        cat $TEMP_DIR/ting-proc-*/results/results.json >> $ALL_RESULTS
        echo $(date) Finished doing $F | tee -a $LOG_FILE
        rm $F
        sleep 10
    done

