#!/bin/bash

pkill -f continuous_sync.py

sleep 2

source venv/bin/activate

nohup python continuous_sync.py > continuous_sync.log 2>&1 &

echo "Continuous sync restarted."
