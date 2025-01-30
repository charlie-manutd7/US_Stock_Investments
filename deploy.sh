#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting deployment process..."

# Ensure we're in the project root
cd "$(dirname "$0")"

# Install Firebase CLI if not installed
if ! command -v firebase &> /dev/null; then
    echo "Installing Firebase CLI..."
    npm install -g firebase-tools
fi

# Build process
echo "🏗️ Building project..."

# Create necessary directories if they don't exist
mkdir -p src/web/static/css
mkdir -p src/web/static/js

# Copy static files
echo "📂 Copying static files..."
cp -r src/web/templates/* src/web/
cp -r src/web/static/* src/web/

# Deploy to Firebase
echo "🚀 Deploying to Firebase..."
firebase deploy

echo "✅ Deployment complete!"
echo "🌎 Your app should be live at: https://us-stock-investments.web.app" 