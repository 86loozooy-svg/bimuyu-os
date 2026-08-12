#!/usr/bin/env bash
# 比目鱼（Bimuyu） 启动脚本 —— 在你自己电脑的终端里运行，独立于 WorkBuddy 会话，常驻不中断。
set -e
cd "$(dirname "$0")"
echo "→ 启动 比目鱼（Bimuyu） (http://localhost:8013)  ..."
exec ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8013
