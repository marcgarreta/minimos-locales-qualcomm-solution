# Kangaroo Path: the Edu-Wifi portal on the UNO Q

A maths practice web app that the Arduino UNO Q serves to anyone who joins its Wi-Fi
(captive portal). Python standard library + SQLite only, no CDN, no internet.

- **Teacher:** adds students (each gets a code like `LUC-123`), uploads problems (text +
  photo; the options are read from the photo with `answer_zone`, the topic is classified
  automatically), sees class statistics.
- **Student:** a Duolingo-style path per topic (8 levels each) showing the class average,
  a radar chart of their levels, and missions: solve on paper, come back, enter the letters.
  Each mistake brings easier, similar problems (embeddings) plus a weekend mission.

## Try it on the laptop

```bash
python arduino/seed/build_seed.py          # once: builds the bank from M3Kang (needs pandas)
python arduino/server.py --port 8000 --dev # http://localhost:8000
```

| Who | Login |
| --- | --- |
| Teacher | user `profe`, password `canguro` (`config.json`) |
| Example students (4º A) | `LUC-123`, `HUG-123`, `MAR-123`, `PAB-123`, `SOF-123` |

The five example students, with three weeks of simulated answers, are created on the first
start (`"demo_students": true`). To start over, delete `arduino/data/`.

Tests (fake bank, no M3Kang data): `cd arduino && python -m unittest discover -s tests`.

## The pieces (each one changes in one place)

| Piece | File | Now | Swap |
| --- | --- | --- | --- |
| Embeddings | `app/embedder.py` | `hash`: words + trigrams, 384 dims | `"embedder": {"kind": "llama"}` uses bge-small on `127.0.0.1:8082` |
| Vector search | `app/vectors.py` | in-memory matrix (numpy if present), vectors stored in SQLite | |
| Classifier | `app/classifier.py` | kNN over the bank: topic, subtopic, level | `"classifier": "none"` removes it |
| First mission | `app/recommender.py` `RandomRecommender` | random, near the starting level | a class with `initial()` |
| Difficulty | `app/difficulty.py` | general difficulty = level + question number (1–228) | |
| Prerequisites | `recommender.prerequisites` | most similar problems a few questions easier, same level first | |
| Weekend mission | `recommender.weekend_task` | prerequisites + practice in weak topics + one challenge | |
| Level per topic | `app/progress.py` | Elo/Rasch `theta` 0–8, not the hardest problem solved | |
| Options from a photo | `app/options.py` | `../answer_zone` when numpy + Pillow + OCR are installed | |

Changing the embedder re-embeds the bank once, on the next start.

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
the laptop with the board's embedding model (bge-small-en-v1.5 Q8_0):

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
