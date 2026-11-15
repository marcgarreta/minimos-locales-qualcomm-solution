#!/bin/bash
# Copy prediction/ (the 2B solver, predict.py, the A53 llama-server) to the board and check it.
#   ./upload_prediction.sh                 # over adb (USB)
#   BOARD=arduino@192.168.1.50 ./upload_prediction.sh   # over SSH
set -e
cd "$(dirname "$0")"
DEST=${DEST:-/home/arduino/prediction}
MODEL=Qwen_Qwen3.5-2B-Q4_0.gguf
if [ -n "$BOARD" ]; then
  ssh "$BOARD" "mkdir -p $DEST ~/models"
  scp -r prediction/* "$BOARD:$DEST/"
  [ -f "models/$MODEL" ] && scp "models/$MODEL" "$BOARD:~/models/" || true
  ssh "$BOARD" "chmod +x $DEST/board/*.sh $DEST/board/bin/*; cd $DEST && ls ~/models/$MODEL || board/download_model.sh"
else
  export MSYS_NO_PATHCONV=1
  adb shell "mkdir -p $DEST ~/models"
  adb push prediction/. "$DEST/"
  [ -f "models/$MODEL" ] && adb push "models/$MODEL" /home/arduino/models/ || true
  adb shell "chmod +x $DEST/board/*.sh $DEST/board/bin/*; sed -i 's/\r$//' $DEST/board/*.sh; ls ~/models/$MODEL || (cd $DEST && board/download_model.sh)"
fi
echo "Uploaded to $DEST. On the board: cd $DEST && board/start_server.sh && python3 predict.py --input problems.jsonl --output predictions.csv"
