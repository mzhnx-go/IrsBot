#!/usr/bin/env bash
# IrsBot 一键停止（macOS / Linux）—— D2.3
# 默认只 down 容器，数据卷保留；加 -v 才会删掉数据库数据。
set -euo pipefail

cd "$(dirname "$0")/.."

echo
echo "  正在停止 IrsBot ..."
docker compose down

echo
echo "  已停止。数据卷 app-db-data 已保留，下次 start 数据还在。"
echo "  彻底清理数据（危险）：docker compose down -v"
echo
