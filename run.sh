#!/bin/bash

# Crypto Dashboard Launcher

echo "🚀 Starting Crypto Trading Dashboard..."
echo ""

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Please run this script from the crypto-dashboard directory"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

# Check if dependencies are installed
if ! python3 -c "import streamlit" &> /dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
    echo ""
fi

# Start the dashboard
echo "✅ Launching dashboard..."
echo "📊 Dashboard will open in your browser at http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo ""

cd dashboard
streamlit run app.py
