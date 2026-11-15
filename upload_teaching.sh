#!/bin/bash
# Deploy teaching/ (Kangaroo Path: Edu-Wifi portal, LED matrix app) to the board and install it.
#   ./upload_teaching.sh                                  # over adb (USB)
#   BOARD=arduino@192.168.1.50 ./upload_teaching.sh       # over SSH
# What goes where:
#   - code: teaching/ from this repo                      -> /home/arduino/edu-portal (the path install.sh uses)
#   - problem bank: M3Kang-derived, research-only, NEVER in git or on the Hub. Built on the laptop with
#     teaching/seed/build_seed.py, build_embeddings.py, build_figures.py; SEED_ASSETS points to it
#   - vendor/: onnxruntime 1.32.0 for the board's Python 3.13 (aarch64), downloaded from PyPI here
#   - models: public GGUFs from Hugging Face (revisions pinned in config.env), downloaded on the board
# The board's data/ (students' database, uploads) is never overwritten. A backup of the old install is kept.
set -e
cd "$(dirname "$0")"
DEST=/home/arduino/edu-portal
SEED_ASSETS=${SEED_ASSETS:-../minimos-locales-qualcomm/arduino/seed}
PY=${PY:-$(command -v python3 || command -v python)}

# 1. vendor/: onnxruntime wheel for linux aarch64, Python 3.13 (no internet needed later on the board)
if [ ! -d .build/vendor/onnxruntime ]; then
  "$PY" -m pip install -q --target .build/vendor --platform manylinux_2_27_aarch64 --platform manylinux_2_28_aarch64 \
    --platform manylinux2014_aarch64 --python-version 3.13 \
    --implementation cp --only-binary=:all: --no-deps onnxruntime==1.32.0
fi

# 2. problem bank (private): check it is there before touching the board
for f in problems.jsonl emb_qwen3.f32 emb_qwen3.json figures.json images; do
  [ -e "$SEED_ASSETS/$f" ] || { echo "missing $SEED_ASSETS/$f: build the bank first (teaching/README.md)"; exit 1; }
done

ON_BOARD='set -e
[ -d ~/edu-portal ] && cp -a ~/edu-portal ~/edu-portal.bak-$(date +%Y%m%d-%H%M%S) || true
source ~/edu-portal/config.env 2>/dev/null || true
mkdir -p ~/models
F=~/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf      # text model of the checker (math-llm, port 8081)
[ -f $F ] || curl -L --retry 3 -o $F https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/resolve/f36b1ea49a332ede8fe5f389bbf5b3575ef71f48/Qwen_Qwen3.5-0.8B-Q8_0.gguf
echo "7182e2362766bb9569209bbc24cf1a4cdfbb8ab161babdb2080c84fa62c08c2f  $F" | sha256sum -c -'

if [ -n "$BOARD" ]; then
  ssh "$BOARD" "$ON_BOARD"
  ssh "$BOARD" "mkdir -p $DEST/seed $DEST/vendor"
  scp -rq teaching/* "$BOARD:$DEST/"
  scp -rq "$SEED_ASSETS"/{problems.jsonl,emb_qwen3.f32,emb_qwen3.json,figures.json,images} "$BOARD:$DEST/seed/"
  scp -rq .build/vendor/* "$BOARD:$DEST/vendor/"
  ssh "$BOARD" "cd $DEST && sed -i 's/\r$//' *.sh && (docker stop edu-portal > /dev/null 2>&1 || true) && sh install.sh"
else
  export MSYS_NO_PATHCONV=1
  adb shell "$ON_BOARD"
  adb shell "mkdir -p $DEST/seed $DEST/vendor"
  adb push teaching/. "$DEST/" > /dev/null
  for f in problems.jsonl emb_qwen3.f32 emb_qwen3.json figures.json images; do
    adb push "$SEED_ASSETS/$f" "$DEST/seed/" > /dev/null
  done
  adb push .build/vendor/. "$DEST/vendor/" > /dev/null
  adb shell "cd $DEST && sed -i 's/\r$//' *.sh && (docker stop edu-portal > /dev/null 2>&1 || true) && sh install.sh"
fi
echo "Teaching app deployed to $DEST. Portal: http://192.168.4.1 on the Edu-Wifi network (see teaching/README.md)."
