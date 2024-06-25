#!/bin/bash
#
# run.sh
# ------
#
# This script runs the web application
#
set -e

# Activate the Virtual Environment
if [ -z "$VIRTUAL_ENV" ]; then
    source bin/activate
fi

python3 web/app.py
