#!/bin/bash
MY_PID=$1
LOCK_FILE=".task_running_$MY_PID"
while true; do
    if [ -f "$LOCK_FILE" ]; then
        sleep 5
        continue
    fi
    echo "- [$(date +%H:%M:%S)] [PID:$MY_PID] 💓 节点心跳正常，当前状态：待命/空闲" >> PROGRESS.md
    sleep 5
done
