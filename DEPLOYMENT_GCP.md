# Deploying Crypto Bot to Google Cloud Platform (GCP)

This guide will help you deploy your trading bot to a **secure, always-on Google Cloud Virtual Machine (VM)**.

## Prerequisites
1.  A Google Cloud Account (Free Tier is sufficient).
2.  `gcloud` CLI installed on your local machine (or use the Cloud Console browser).
3.  Your Telegram Token and Chat ID ready.

---

## Step 1: Create a Virtual Machine (VM)
We will use a small, cost-effective Linux server.

1.  Go to **GCP Console > Compute Engine > VM Instances**.
2.  Click **Create Instance**.
3.  **Name:** `crypto-trading-bot`
4.  **Region:** Choose usually `us-central1` or close to you.
5.  **Machine Type:** `e2-micro` (often Free Tier eligible) or `e2-small` ($15/mo).
6.  **Boot Disk:** Change to **Ubuntu 22.04 LTS** (Standard Persistent Disk 30GB).
7.  **Firewall:** No HTTP/HTTPS needed (it's a backend bot).
8.  Click **Create**.

---

## Step 2: Prepare Your Code for Upload
1.  On your local machine, open terminal in `crypto-dashboard`.
2.  Make sure your `.env` file has your PROD keys:
    ```bash
    TELEGRAM_TOKEN=your_token
    TELEGRAM_CHAT_ID=your_id
    BINANCE_API_KEY=...
    BINANCE_SECRET=...
    ```
3.  Zip your project (excluding heavy virtual environments):
    ```bash
    zip -r crypto_bot.zip . -x "venv/*" -x ".git/*" -x "__pycache__/*"
    ```

---

## Step 3: Fast Deployment (Recommended)
We have created an automated script `deploy_remote.sh` for one-click updates.

1.  **Configure Script**: Open `deploy_remote.sh` and set your `VM_NAME` and `ZONE`.
2.  **Make Executable**:
    ```bash
    chmod +x deploy_remote.sh
    ```
3.  **Run Deployment**:
    ```bash
    ./deploy_remote.sh
    ```
    This script will:
    - Package your code.
    - Upload to VM.
    - Preserve your database and `.env` file (so you don't lose data).
    - Rebuild and restart the Docker container.

## Step 4: First-Time Setup Only
If this is your **very first run**, you need to set up the environment variables on the server manually *once* before the script works perfectly.

1.  Connect to VM: `gcloud compute ssh crypto-trading-bot`
2.  Install Docker:
    ```bash
    sudo apt-get update && sudo apt-get install -y docker.io unzip
    sudo usermod -aG docker $USER
    newgrp docker
    ```
3.  Create `.env` file:
    ```bash
    nano .env
    # Paste your TELEGRAM_TOKEN, CHAT_ID, API Keys here
    # Ctrl+O to save, Ctrl+X to exit
    ```
4.  Run `./deploy_remote.sh` from your local machine.

## Step 5: Monitoring

---

## Step 5: Monitoring & Commands

- **View Live Logs:** `sudo docker logs -t -f trader`
- **Stop Bot:** `sudo docker stop trader`
- **Restart Bot:** `sudo docker restart trader`
- **Update Code:**
  1. Upload new zip.
  2. Unzip over existing folder.
  3. `sudo docker build -t crypto-bot .`
  4. `sudo docker rm -f trader` (delete old container)
  5. Run the `docker run` command from Step 4 again.

---

## Step 6: Verify Telegram
You should receive a **"💓 SYSTEM PULSE"** message on Telegram immediately, and then every hour.

**✅ Deployment Complete!**
Your bot is now running 24/7 in the cloud.
