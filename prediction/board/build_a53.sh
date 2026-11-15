#!/bin/bash
# Cross-compile llama.cpp b12383 for the UNO Q's Cortex-A53 (ARMv8.0, no dotprod), on a Linux/WSL laptop.
# Static binaries: copy them to the board and run them directly, no Docker and no compiler needed there.
#   sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu cmake ninja-build git python3
#   ./build_a53.sh            -> build/bin/llama-server, build/bin/llama-bench
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${SRC:-$HOME/llama.cpp-a53}
if [ ! -d "$SRC" ]; then
  git init -q "$SRC" && cd "$SRC"
  git remote add origin https://github.com/ggml-org/llama.cpp.git
  git fetch -q --depth 1 origin tag b12383 && git checkout -q FETCH_HEAD
  python3 "$HERE/patch_sgemm.py" ggml/src/ggml-cpu/llamafile/sgemm.cpp
fi
cd "$SRC"
cat > tc.cmake <<'TC'
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
TC
GOMP=$(aarch64-linux-gnu-gcc -print-file-name=libgomp.a)
cmake -S . -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=tc.cmake -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF \
  -DGGML_CPU_ARM_ARCH=armv8-a -DCMAKE_C_FLAGS="-mcpu=cortex-a53" -DCMAKE_CXX_FLAGS="-mcpu=cortex-a53" \
  -DBUILD_SHARED_LIBS=OFF -DCMAKE_EXE_LINKER_FLAGS="-static" -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
  -DGGML_OPENMP=ON -DLLAMA_BUILD_TESTS=OFF
sed -i "s#[^ ]*libgomp.so#$GOMP#g" build/build.ninja   # link OpenMP statically too
cmake --build build -j"$(nproc)" --target llama-server llama-bench
ls -la build/bin/llama-server build/bin/llama-bench
