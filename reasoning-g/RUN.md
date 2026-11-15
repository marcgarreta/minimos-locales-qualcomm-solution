# Submission package — fine-tuned Qwen3-1.7B (Datathon FME 2026, reasoning exam)

Getting the model (1.1 GB, too big for git): it is a release asset of this private repo.
```bash
gh release download model-v1 -R marcgarreta/minimos-locales-qualcomm-solution -p '*.gguf' -D reasoning/model
shasum -a 256 reasoning/model/student-final-Q4_K_M.gguf   # Linux: sha256sum; must match the sha256 below
```
Then run everything below from the `reasoning/` folder.

Contents
- `model/student-final-Q4_K_M.gguf` — fine-tuned Qwen3-1.7B (QLoRA on verified Qwen3.5-4B solutions, eng+cat).
  sha256 `f2a392c18c462e5febcc368e44ad43a838e32d4627a6ac20c44b8bcab96d20bf`
- `repo_official/` — the exact submission code: `predict.py`, `eval.py`, `copilot/` (reasoning solver), `config.env`,
  `board/06_install_submission.sh` (installs the model service), `board/07_measure_speed.py` (board speed → config.env).
- `src/eval_practice.py` + `data/practice/` — organisers' 2026 practice set (100 rows, eng+cat, with images) to measure
  accuracy and projected board time. `reference_results_43of100.jsonl` = our run (43/100, all ≤60 s projected).

Needs: Python 3 (standard library only) and llama.cpp at the board's pinned commit `2cbe0ec` (already on the board).

## A. On the Arduino UNO Q (the real test)
```bash
mkdir -p ~/models && cp model/student-final-Q4_K_M.gguf ~/models/
cp -r repo_official/copilot repo_official/config.env repo_official/predict.py repo_official/board \
      ~/datathon-UPC-maths-qualcomm-arduino-unoq/          # the board's clone of the official repo
cd ~/datathon-UPC-maths-qualcomm-arduino-unoq
bash board/06_install_submission.sh                       # text model on port 8081 (no vision server, by design)
python3 board/07_measure_speed.py                         # put the printed LLM_READ_TPS / LLM_WRITE_TPS in config.env
python3 predict.py --input <prepared practice>/train.jsonl --output results/practice.csv
```
Check in the CSV: every `seconds` < 60, one letter per row. (Practice input as the organisers prepare it:
`python3 laptop/prepare_m3kang.py --parquet data/demo-00000-of-00001.parquet --languages eng,cat --val-fraction 0 --out data/demo --save-images`)

## B. On a laptop (same code, projected board time)
```bash
# build the pinned llama.cpp once
git init llama.cpp && cd llama.cpp && git remote add origin https://github.com/ggml-org/llama.cpp.git
git fetch --depth 1 origin 2cbe0ec429b849a88664e0f62388fc92a5abd699 && git checkout FETCH_HEAD
cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j --target llama-server && cd ..
# serve the model with the board's flags (4 threads, CPU)
llama.cpp/build/bin/llama-server -m model/student-final-Q4_K_M.gguf --port 8081 --host 127.0.0.1 --threads 4 \
   --ctx-size 2048 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 --seed 42 &
# accuracy on the practice set (real pipeline; prints by language/level, statuses, projected board seconds)
VISION_PORT=9 python3 src/eval_practice.py --input data/practice/records.jsonl --name check
# or exactly what the organisers run:
cd repo_official && python3 predict.py --input ../data/practice/records.jsonl --output ../practice.csv
```
Expected (laptop, projected board time): ~43/100, English ~26/50, Catalan ~17/50, max projected ~51 s.

## How it answers (for context)
One line of reasoning then a forced letter (grammar), time budget per problem from `LLM_READ_TPS`/`LLM_WRITE_TPS`;
if the budget runs out, the letter is read by continuing the same text (cache reuse, ~1 s); every request stops at the
deadline (60 s − 5 s margin) and the default letter is answered. Figure problems use the text route (question + options).
Settings: `repo_official/config.env` (`SOLVER=baseline` restores the organisers' one-letter baseline).
Do not share outside the team: the model was trained on M3Kang (research-only licence).
