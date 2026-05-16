#!/bin/bash
# Usage: ./set_telegram_webhook.sh <bot_token> <webhook_url>
BOT_TOKEN=$1
WEBHOOK_URL=$2

if [ -z "$BOT_TOKEN" ] || [ -z "$WEBHOOK_URL" ]; then
  echo "Usage: $0 <bot_token> <webhook_url>"
  exit 1
fi

curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" -d "url=${WEBHOOK_URL}"