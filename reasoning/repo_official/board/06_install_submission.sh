#!/bin/bash
# Install the submission model services on the UNO Q (run ON THE BOARD after steps 00-05).
#
# Before running, copy from the laptop into ~/models/ on the board:
#   student-final-Q4_K_M.gguf            (fine-tuned Qwen3-1.7B, or Qwen_Qwen3-1.7B-Q4_K_M.gguf for the base)
#   mmproj-Qwen_Qwen3.5-0.8B-f16.gguf    (vision projector; README "Let the model see the image" step)
# e.g.  scp tools/models/student_final/student-final-Q4_K_M.gguf arduino@<ip>:~/models/
#
# Usage: bash board/06_install_submission.sh [TEXT_GGUF_FILENAME] [--with-vision]
# DEFAULT = TEXT ONLY: figure problems go through the text route. Measured on the 20 practice figure rows:
#   text route 6/20, Qwen3.5-0.8B vision full page 5/20 (answered E 19/20), cropped diagram 6/18 -> vision adds nothing
#   measurable, and a second server costs ~1.3 GB of the board's ~3.1 GB available RAM.
# Text model  : port 8081 (math-llm.service, replaces the 0.8B text service)
# Vision model: port 8083 (math-vision.service, Qwen3.5-0.8B + mmproj, 128 image tokens)
# ctx-size 2048 for both to keep RAM within the board's ~3.1 GB available (laptop RSS: ~1.2 GB + ~0.5 GB).
# The embedding service is not needed by predict.py and is stopped to free RAM.
set -euo pipefail
TEXT=${1:-student-final-Q4_K_M.gguf}
VISION=0; [ "${2:-}" = "--with-vision" ] && VISION=1
M=/home/arduino/models
B=/home/arduino/llama.cpp/build/bin/llama-server
NEEDED=("$M/$TEXT"); [ $VISION = 1 ] && NEEDED+=("$M/Qwen_Qwen3.5-0.8B-Q8_0.gguf" "$M/mmproj-Qwen_Qwen3.5-0.8B-f16.gguf")
for f in "${NEEDED[@]}"; do
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
done
COMMON="--host 127.0.0.1 --threads 4 --ctx-size 2048 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 --seed 42"
sudo tee /etc/systemd/system/math-llm.service > /dev/null <<EOF
[Unit]
Description=Math on the Edge: text model (port 8081)
After=local-fs.target
[Service]
Type=simple
User=arduino
ExecStart=$B -m $M/$TEXT --port 8081 $COMMON
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/math-vision.service > /dev/null <<EOF
[Unit]
Description=Math on the Edge: vision model Qwen3.5-0.8B + mmproj (port 8083)
After=local-fs.target
[Service]
Type=simple
User=arduino
ExecStart=$B -m $M/Qwen_Qwen3.5-0.8B-Q8_0.gguf --mmproj $M/mmproj-Qwen_Qwen3.5-0.8B-f16.gguf --image-max-tokens 128 --port 8083 $COMMON
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl disable --now math-embed || true
if [ $VISION = 1 ]; then
  sudo systemctl enable --now math-llm math-vision
else
  sudo systemctl disable --now math-vision 2>/dev/null || true
  sudo systemctl enable --now math-llm
fi
sleep 15
systemctl is-active math-llm
curl -s http://127.0.0.1:8081/health; echo
[ $VISION = 1 ] && { curl -s http://127.0.0.1:8083/health; echo; }
free -m
echo "If free memory is very low or a service restarts, keep text only: sudo systemctl disable --now math-vision"
echo "(predict.py then answers figure problems through the text route automatically)."
