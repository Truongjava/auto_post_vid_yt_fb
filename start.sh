#!/bin/bash
set -e

echo "========================================="
echo "  Auto Upload Pipeline - Web Service"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

# Ghi secrets ra file (giống GitHub Actions)
if [ -n "$CLIENT_SECRET_JSON" ]; then
    echo "$CLIENT_SECRET_JSON" > client_secret.json
    echo "✅ Đã tạo client_secret.json"
else
    echo "⚠️  Không có CLIENT_SECRET_JSON (YouTube sẽ không hoạt động)"
fi

if [ -n "$TOKEN_JSON" ]; then
    echo "$TOKEN_JSON" > token.json
    echo "✅ Đã tạo token.json"
else
    echo "⚠️  Không có TOKEN_JSON (YouTube sẽ không hoạt động)"
fi

echo "🚀 Khởi động Web Server..."
python app.py
