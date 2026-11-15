#!/bin/bash
# On the board or the laptop: download the pinned 2B Q4_0 and check its SHA-256 (needs network once, not at run time).
set -e
source "$(dirname "$0")/../config.env"
mkdir -p ~/models
F=~/models/$LLM_FILE
[ -f "$F" ] || curl -L --retry 3 -o "$F" "https://huggingface.co/$LLM_REPO/resolve/$LLM_REVISION/$LLM_FILE"
echo "$LLM_SHA256  $F" | sha256sum -c -
