#!/bin/bash
# Copy teaching/ (the Kangaroo Path web app: portal, LED matrix app, seed) to the board and install it.
#   ./upload_teaching.sh                   # over adb (USB)
#   BOARD=arduino@192.168.1.50 ./upload_teaching.sh     # over SSH
set -e
cd "$(dirname "$0")"
DEST=${DEST:-/home/arduino/edu-portal}  # teaching/install.sh installs from this path
if [ -n "$BOARD" ]; then
  ssh "$BOARD" "mkdir -p $DEST"
  scp -r teaching/* "$BOARD:$DEST/"
  ssh "$BOARD" "cd $DEST && chmod +x *.sh && sh install.sh"
else
  export MSYS_NO_PATHCONV=1
  adb shell "mkdir -p $DEST"
  adb push teaching/. "$DEST/"
  adb shell "cd $DEST && sed -i 's/\r$//' *.sh && chmod +x *.sh && sh install.sh"
fi
echo "Teaching app installed from $DEST (see teaching/README.md)."
