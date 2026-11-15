# Kangaroo Path: the Edu-Wifi portal on the UNO Q

A maths practice web app that the Arduino UNO Q serves to anyone who joins its Wi-Fi
(captive portal). Python standard library + SQLite only, no CDN, no internet.

- **Teacher:** adds students (each gets a code like `LUC-123`), uploads problems (text +
  photo; the team's OCR cuts out the figure and reads the options, the topic is classified
  automatically), sees class statistics.
- **Student:** a Duolingo-style path per topic (8 levels each) showing the class average,
  a radar chart of their levels, and missions: solve on paper, come back, enter the letters.
  Each mistake brings easier, similar problems (embeddings) plus a weekend mission.

## Try it on the laptop

```bash
python arduino/seed/build_seed.py          # once: builds the bank from M3Kang (needs pandas)
python arduino/seed/build_embeddings.py    # once: the bank's Qwen3-Embedding vectors
python arduino/seed/build_figures.py       # once: figures + option crops from the OCR handoff
python arduino/server.py --port 8000 --dev # http://localhost:8000
```

| Who | Login |
| --- | --- |
| Teacher | user `profe`, password `canguro` (`config.json`) |
| Example students (4º A) | `LUC-123`, `HUG-123`, `MAR-123`, `PAB-123`, `SOF-123` |
| Demo student (no history, fixed mission) | `DEM-123` (Elena Ruiz) |

The five example students, with three weeks of simulated answers, and the demo student are
created on the first start (`"demo_students": true`). To start over:
`python arduino/server.py --reset-demo` (moves the database to `data/backup/<time>/`), then start
the server again.

Tests (fake bank, no M3Kang data): `cd arduino && python -m unittest discover -s tests`.

## Demo: the calculation check (reproducible)

`DEM-123` always starts with the same mission (`app/demo.py`). Problem 1 (Geometría plana · Nivel 1 ·
pregunta 16): *a 15 × 9 cm rectangle loses a square of perimeter 8 cm at each corner; what is the
perimeter?* The answer is A) 48 cm, because cutting the corners doesn't change it: 2 × (15 + 9) = 48.

1. Log in as `DEM-123`, open **Responder misión**, pick **B (40 cm)** and **Comprobar**: red.
2. **✎ Explicar cómo lo hice** and write exactly:
   `Recortar las esquinas no cambia el perímetro. 15 + 9 = 20 y 2 x 20 = 40 cm.`
3. **Revisar mis cálculos**, then answer or **Saltar** the other four and **Entregar misión**.
4. In **Corrección**, after about 10 s on the board: **20** is red (15 + 9 is 24), and 15, 9, 2,
   20 and 40 are green ("Revisa el número marcado en rojo").

Measured with the board's Qwen3.5 0.8B (temperature 0, so it repeats): the 20 scores 9.1 nats
(threshold 5) and every other number less than 2. With `= 24 y 2 x 24 = 40` the 40 is the red one,
and with the right `= 24 y 2 x 24 = 48` nothing is red. To repeat the demo, on the board:
`docker exec edu-portal python3 /portal/server.py --reset-demo && docker restart edu-portal`.

## Answering a mission

The student solves on paper and then, one problem at a time: picks the option (square tiles
showing each option as printed: text, fraction or drawing), presses **Comprobar** and sees it
green or red at once, with the right answer. A checked answer is locked (the server keeps the
first one). **Saltar** skips a problem: it isn't graded and comes back first in the next mission.
Keys: A–E or 1–5 choose, Enter checks / continues, S skips. Tapping a statement opens the original
page with zoom.

After a red answer the student can, **optionally**, write how they solved it (**✎ Explicar cómo lo
hice**, also in the *Corrección* of the result page). The board's LLM checks the **numbers** in
the background (`app/checker.py`, one job at a time, resumed after a restart) and the correction
shows them green, or red when one is probably a wrong result. It reads the problem, the right
answer and the text, and takes the surprise −log p of every digit by teacher forcing; a digit
above `threshold` (5 nats) is flagged. Words are ignored: other people's wording is always
surprising, a wrong result isn't. It catches calculation slips, not reasoning mistakes. On 114
solutions written by another model it flagged 80% of those with one calculation slip and 5% of
the correct ones (`experiments/ppl` in the datathon folder). Needs the Qwen3.5 llama-server
(`LLM_PORT`, started with `--jinja`); without it the explanation is saved and marked as not checked.

## Figures: the text once, then only the picture

A problem shows its text once, then only what the text can't say: the figure cut out of the
page and, when the options are pictures, one crop per option (otherwise the options read by OCR
as text tiles). The zoom always shows the original page. This is the team's OCR handoff,
vendored unchanged in `ocr_handoff/` (`answer_zone` with PP-OCRv4 on onnxruntime, plus
`src/export_multimodal.py`); `app/figures.py` only adapts its output.

- **The bank:** `seed/build_figures.py` reads the handoff's `answer_zone_multimodal_all.jsonl`
  and writes `seed/figures.json` + `seed/multimodal/` (crops in 16 greys, 14 MB). Of 1,747
  problems: 797 text only, 652 figure + text options, 139 figure + option crops, 78 option
  crops only, 81 fall back to the whole page.
- **A teacher's photo:** `add_problem` runs the same pipeline on the board (about 4 s on the
  UNO Q's CPU, no GPU needed) and saves the crops in `data/ocr/`; options the teacher left
  empty are filled from the OCR. `/api/extract-options` uses it to prefill the form.
- Needs `onnxruntime` (in `vendor/`, see *On the board*) and the model
  `ocr_handoff/minimos-locales-qualcomm/answer_zone/models/ch_PP-OCRv4_rec_infer.onnx`
  (git-ignored). Without them a photo is shown whole and the options are typed by hand.

## The pieces (each one changes in one place)

| Piece | File | Now | Swap |
| --- | --- | --- | --- |
| Embeddings | `app/embedder.py` | Qwen3-Embedding-0.6B Q8_0, no prompt, 1024 dims (see below) | `"kind": "llama"` for another llama.cpp model, `"kind": "hash"` for none |
| Vector search | `app/vectors.py` | in-memory matrix (numpy if present), vectors stored in SQLite | |
| Classifier | `app/classifier.py` | kNN over the bank: topic, subtopic, level | `"classifier": "none"` removes it |
| First mission | `app/recommender.py` `RandomRecommender` | random, near the starting level | a class with `initial()` |
| Difficulty | `app/difficulty.py` | general difficulty = level + question number (1–228) | |
| Prerequisites | `recommender.prerequisites` | most similar problems a few questions easier, same level first | |
| Weekend mission | `recommender.weekend_task` | prerequisites + practice in weak topics + one challenge | |
| Level per topic | `app/progress.py` | Elo/Rasch `theta` 0–8, not the hardest problem solved | |
| Figure + options from a photo | `app/figures.py` | the team's OCR handoff in `ocr_handoff/` (onnxruntime) | `"ocr_handoff_path"` in `config.json` |
| Calculation check | `app/checker.py` | Qwen3.5 0.8B on `127.0.0.1:8081`, digits above 5 nats | `"checker": {"kind": "none"}` turns it off |

Changing the embedder re-embeds the bank once, on the next start.

## Embeddings: Qwen3-Embedding-0.6B

Every similarity in the app (similar problems, prerequisites, missions, classifier, 3D map)
uses **Qwen3-Embedding-0.6B Q8_0** without an instruction prompt (best retrieval in our
benchmark: 0.94 cross-language recall), last-token pooling, 1024 dimensions.

- **The bank is precomputed** on the laptop, so the board never has to embed 1,747 problems:
  `python arduino/seed/build_embeddings.py` writes `seed/emb_qwen3.f32` + `.json` (git-ignored)
  from `results/emb/qwen3doc-0.6b-q8.npy`. Those vectors match `llama-server` exactly (cosine 1.0000).
- **New texts** (problems the teacher adds, live classification) go to a llama.cpp server:

  ```bash
  llama-server -m Qwen3-Embedding-0.6B-Q8_0.gguf --embedding --pooling last --port 8082 -c 2048 -ub 2048
  ```

- **If that server doesn't answer** (today the board has no llama.cpp), a new text gets the
  similarity-weighted mean of the Qwen vectors of the bank problems with the closest wording.
  It is stored as `qwen3-embedding-0.6b~approx` and redone with the real model on the first
  start where the server answers. The app retries the server every 5 minutes.

## Difficulty and the 3D map

The number after the last `_` in an M3Kang id is the question number, and each exam goes from
easy to hard. Levels 0–1 have 24 questions and levels 2–7 have 30, so the **general difficulty**
stacks them: level 0 question 8 → 8, level 1 question 3 → 24 + 3 = 27, level 2 question 1 → 49,
up to 228. "A little harder/easier" means a few questions up/down inside the same level; only
the last (or first) questions of a level reach into the next (or previous) one.

**Mapa 3D** (student and teacher tab): for one topic, height = general difficulty, with a plane
where each level starts. Every problem keeps its place in **one UMAP fitted on the whole
topic**, so similar problems sit at the same spot at any height. Arrows go to the 2 most
similar problems a few questions harder (93 % stay in the same level).

- Student: solved (turquoise) and failed (orange) problems form your tree; yellow dashed
  arrows are similar, slightly harder problems to try next; rings mark your current mission.
- Teacher: point size = attempts, colour = class accuracy.
- Hover a plane or a point to light up that level. Click a problem to zoom into its difficulty
  and the ones just below and above (▼ ▲ to move, colours kept); click outside, ✕ or Escape
  to see the whole ladder again.

It is drawn with plain canvas 2D (no libraries, works offline). The layout is precomputed on
the laptop with the same Qwen3-Embedding vectors as the app:

```bash
python arduino/seed/build_layout.py     # writes seed/layout.json (ids, 2D positions, arrows; no text)
```

Problems added later by the teacher are placed at the weighted mean of their nearest
neighbours, and their arrows use the app's embedder.

## The problem bank

`seed/build_seed.py` joins `seed/categories_eng.json` (topic, subtopic and level of each
problem), the English text and answer from `data/texts.parquet`, the image, and the options
read with `answer_zone`, into `seed/problems.jsonl` + `seed/images/`. The server imports it
on the first start. **M3Kang is research-only**: `seed/problems.jsonl`, `seed/images/` and
`data/` are in `.gitignore`.

## On the board

`compose.yaml` mounts the code read-only and `./data` writable (database and uploaded
photos). Copy `arduino/` (with `seed/`) to `/home/arduino/edu-portal` and run
`sh install.sh` once (it sets up the Wi-Fi and starts the container). To update later:
copy the files again and `docker compose up -d --force-recreate` in that folder.

The OCR needs `onnxruntime`, which the image doesn't have and the board can't download. Copy the
`onnxruntime-1.32.0-cp313-cp313-manylinux_2_27_aarch64...whl` wheel to the board and install it
into `vendor/` (the app adds `vendor_path` to `sys.path`):

```bash
docker run --rm -v ~/edu-portal:/w ghcr.io/arduino/app-bricks/python-apps-base:0.5.0   pip install --no-deps --no-index --target /w/vendor /w/onnxruntime-1.32.0-*.whl
```

The calculation check needs Qwen3.5 0.8B on `127.0.0.1:8081`. The board has no compiler and no
internet, so it runs the prebuilt `llama-b12383-bin-ubuntu-arm64.tar.gz` from the llama.cpp releases
(unpacked in `~/llama.cpp/`, with the GGUF in `~/models/`) as a container that starts on boot:
see `llm/compose.yaml`. It uses about 0.9 GB of RAM and checks a short explanation in 10–30 s.

The board has no battery-backed clock and no internet, so after a reboot it may think it is
1970. The first login sends the browser's time and the server corrects itself (only when its
own clock is before 2025), so due dates and streaks stay right.

## The LED matrix (`matrix/`)

An App Lab app that shows what the portal is doing. Python polls `GET /api/board` (counters
only, no names or codes) every 2 s and draws ~12 frames per second; the sketch asks for each
frame with `Bridge.call("frame")` and copies it to the 8x13 matrix in 8 levels of brightness.

| Scene (rotating) | Shows |
| --- | --- |
| Signal bars + number | devices connected to Edu-Wifi (DHCP leases) |
| Person + number | students active in the last 5 minutes |
| Tick + number | missions handed in today |
| Equaliser | average level of the class in each of the 9 topics |
| `62%` + bar | today's accuracy |
| Kangaroo | hops across while idle |

Events interrupt it: a mission handed in plays a burst and the score (`6/8`, stars if
perfect), a student logging in sends the kangaroo across, a new student or problem shows `+1`.
While the portal is starting a bar sweeps; if it stops answering, a sad face breathes slowly.

Install on the board (over adb, `TMPDIR` must point to `/tmp`):

```bash
cp -r arduino/matrix ~/ArduinoApps/kangaroo-matrix
TMPDIR=/tmp arduino-app-cli app start user:kangaroo-matrix
TMPDIR=/tmp arduino-app-cli properties set default user:kangaroo-matrix   # start it at boot
```

`sketch/libraries/ArxTypeTraits` is ArxTypeTraits 0.3.1 (MIT, hideakitai), a dependency of
the Bridge that the offline board can't download. The app's container reaches the portal
through its Docker gateway (the portal runs with `network_mode: host`).
