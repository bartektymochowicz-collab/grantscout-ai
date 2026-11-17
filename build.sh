#!/usr/bin/env bash
# Skrypt budowania dla Render.com (Build Command: ./build.sh)
set -o errexit

pip install -r backend/requirements.txt

cd frontend && npm install && npm run build
