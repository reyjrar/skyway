#!/bin/bash
#
# setup.sh
# --------
#
# This script sets up docker, downloads the raw data file,
# starts ClickHouse, configures the venv, and then imports
# the data into ClickHouse.
#
set -e

if [ ! -f "./docker-compose.yaml" ]; then
    echo "Run from the directory with the docker-compose.yaml!"
    exit 1;
fi

echo "Verifying data directories .."
for dir in 'chdata' 'import'; do
    if [ ! -d "$dir" ]; then
        mkdir "$dir"
        echo "+ created data directory $dir"
    fi
done
echo " .. done."

import_file="import/AWSCUR.snappy.parquet"
import_source='https://file.notion.so/f/f/0d01df87-37dc-4c63-828d-f136594e6066/cf5fb938-4484-4b05-bfbb-61fa1dbe7ba6/Oct2018-WorkshopCUR-00001.snappy.parquet?id=598fbdc5-46db-4830-a73e-752b01639cff&table=block&spaceId=0d01df87-37dc-4c63-828d-f136594e6066&expirationTimestamp=1719172800000&signature=QgwBzD8oL1lHK6G3lQOhWtzpQmgiom3XSyIVthWew_I&downloadName=Oct2018-WorkshopCUR-00001.snappy.parquet'

if [ ! -f "$import_file" ]; then
    echo -n "Missing data file, downloading .."
    if wget -O "$import_file" "$import_source"; then
        echo "done!"
    else
        echo "FAILED to retrieve data file, please download to $import_file before proceeding";
        exit 2;
    fi
else
    echo "Data file found, skipping.."
fi

# Start up clickhouse
project_name=$(basename "$PWD")
echo "\nchecking ${project_name} status..";
output=$(docker-compose -p "$project_name" kill --dry-run 2>&1)

if [[ $output == "no container to kill" ]]; then
    echo " - ${project_name} is not started, starting"
    docker-compose up -d
fi

clickhouse=""
running_containers=$(docker-compose ps --format=json | jq -r 'select(.State == "running") | .Name')
while read name; do
    if [[ $name == "${project_name}-clickhouse-"* ]]; then
        clickhouse="$name"
    fi
done <<< "$running_containers"

if [ -z "$clickhouse" ]; then
    echo "!! ClickHouse ($clickhouse)is not running, please fix that, and re-run !!";
    exit 3;
fi

# Install venv
if [ ! -f './pyvenv.cfg' ]; then
    echo "Setting up venv"
    python3 -m venv .
fi;

# Activate the Virtual Environment
if [ -z "$VIRTUAL_ENV" ]; then
    source bin/activate
fi

# Install requirements
pip3 --require-venv install -r ./requirements.txt

echo "Reloading the dataset"
echo ""
python3 ./import_data.py
