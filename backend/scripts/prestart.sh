#! /usr/bin/env bash

set -e
set -x

# Let the DB start
python scripts/pre_start.py

# Run migrations
alembic upgrade head

# Create initial data in DB
python scripts/init_data.py
