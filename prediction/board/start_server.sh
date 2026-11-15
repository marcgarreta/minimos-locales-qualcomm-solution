#!/bin/bash
# On the board: serve Qwen3.5 2B Q4_0 with the A53 build (board/bin/llama-server) on 127.0.0.1:8081.
# Stops the official text server first (systemd service or Docker container), since it uses the same port.
HERE=$(cd "$(dirname "$0")" && pwd)
MODEL=${MODEL:-$HOME/models/Qwen_Qwen3.5-2B-Q4_0.gguf}
sudo -n systemctl stop math-llm 2>/dev/null; docker stop math-llm > /dev/null 2>&1
pkill -f "board/bin/llama-server" 2>/dev/null; sleep 1
nohup "$HERE/bin/llama-server" -m "$MODEL" --host 127.0.0.1 --port 8081 --threads 4 --ctx-size 4096 --parallel 1 \
  --cache-ram 0 --ctx-checkpoints 8 --jinja --reasoning off --reasoning-budget 0 --alias qwen3.5-2b \
  > "$HERE/server.log" 2>&1 < /dev/null &
until curl -s 127.0.0.1:8081/health | grep -q ok; do sleep 2; done
echo "2B server ready on 127.0.0.1:8081 (log: $HERE/server.log)"
