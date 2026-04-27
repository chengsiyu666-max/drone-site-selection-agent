#!/bin/bash
# 一键更新脚本 —— 在本地运行,会 push 代码到服务器并重启 Flask
# 用法: ./deploy.sh "提交信息"

set -e

SERVER="<YOUR_SERVER_USER>@<YOUR_SERVER_IP>"
KEY="<YOUR_PRIVATE_KEY_PATH>"
REPO_DIR="<YOUR_LOCAL_REPO_PATH>"

MSG="${1:-update}"

cd "$REPO_DIR"

if [[ -n $(git status --porcelain) ]]; then
  git add -A
  git commit -m "$MSG"
else
  echo "(没有本地改动,仅触发服务器重启)"
fi

GIT_SSH_COMMAND="ssh -i $KEY" git push origin main

ssh -i "$KEY" "$SERVER" 'cd ~/site-selection-app && git pull -q origin main && ./start.sh && sleep 1 && tail -5 flask.log'

echo ""
echo "✅ 部署完成 → http://<YOUR_SERVER_IP>:5001"
