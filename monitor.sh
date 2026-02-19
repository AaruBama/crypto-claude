#!/bin/bash

# ==========================================
# 📺 LIVE MONITORING SCRIPT
# ==========================================
# Connects to your GCP Bot and streams logs.
# Usage: ./monitor.sh
# ==========================================

VM_NAME="crypto-trading-bot"
ZONE="asia-south1-a"
PROJECT_ID="crypto-project-487912"

echo "📡 Connecting to $VM_NAME logs..."
echo "Use Ctrl+C to stop watching (bot will keep running)."

gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="sudo docker logs -f --tail 100 trader"
