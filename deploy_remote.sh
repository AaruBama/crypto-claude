#!/bin/bash

# ==========================================
# 🚀 GCP AUTO-DEPLOYMENT SCRIPT
# ==========================================
# Usage: ./deploy_remote.sh
# 
# PEREQUISITES:
# 1. Update VM_NAME and ZONE below to match your GCP instance.
# 2. Run `gcloud auth login` once if not logged in.
# ==========================================

# --- CONFIGURATION (UPDATE THESE) ---
VM_NAME="crypto-trading-bot"
ZONE="asia-south1-a"  # Mumbai Zone
PROJECT_ID="crypto-project-487912" # Explicit Project ID to avoid permission errors
# ------------------------------------

echo "🚀 Starting Deployment to $VM_NAME ($ZONE) in project $PROJECT_ID..."

# 1. Package Code
echo "📦 Zipping project (excluding heavy/local files)..."
rm -f crypto_bot_deploy.zip
zip -r -q crypto_bot_deploy.zip . -x "venv/*" -x ".git/*" -x "__pycache__/*" -x "data/*" -x "*.DS_Store" -x "deploy_remote.sh"

# 2. Upload to VM
echo "📤 Uploading zip to VM..."
gcloud compute scp crypto_bot_deploy.zip $VM_NAME:~ --zone=$ZONE --project=$PROJECT_ID --quiet
if [ $? -ne 0 ]; then
    echo "❌ Upload failed. Check VM_NAME, ZONE, and PROJECT_ID."
    exit 1
fi

# 3. Remote Execution (Safe Swap & Restart)
echo "🔄 Executing remote update..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="
    # 1. Unzip to temporary folder
    sudo rm -rf bot_new
    unzip -q crypto_bot_deploy.zip -d bot_new
    
    # 2. Safety: Copy existing Data & Config from current deployment
    if [ -d bot ]; then
        echo '🛡️ Preserving existing database and .env...'
        # Copy .env
        [ -f bot/.env ] && sudo cp bot/.env bot_new/
        [ -f bot/trading_engine/db.sqlite ] && sudo cp bot/trading_engine/db.sqlite bot_new/trading_engine/
    else
        echo '✨ First deployment detected.'
        # For first run, user must create .env manually or we copy local .env if included in zip
    fi

    # 3. Swap Directories (Atomic-ish switch)
    sudo rm -rf bot_old
    [ -d bot ] && sudo mv bot bot_old
    sudo mv bot_new bot

    # 4. Docker Rebuild & Restart
    cd bot
    echo '🐳 Building Docker container...'
    sudo docker build -t crypto-bot .
    
    echo '🛑 Restarting service...'
    sudo docker stop trader 2>/dev/null || true
    sudo docker rm trader 2>/dev/null || true
    
    # Run new container (Persist DB via volume map just in case)
    sudo docker run -d \
      --restart unless-stopped \
      --name trader \
      --env-file .env \
      -v \$(pwd)/trading_engine/db.sqlite:/app/trading_engine/db.sqlite \
      -v \$(pwd)/logs:/app/logs \
      crypto-bot

    echo '✅ Service started!'
"

echo "🎉 Deployment Complete! Bot is updating in the background."
