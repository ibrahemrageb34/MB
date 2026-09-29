#!/bin/sh
# Daily run on a Mac/Linux laptop until the server is ready (crontab -e: 0 8 * * * /path/MB/deploy/run_daily.sh)
cd "$(dirname "$0")/.." && python3 -m mbos run && python3 -m mbos alerts --kind prepaid
