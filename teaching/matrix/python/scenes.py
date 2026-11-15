"""Pictures and animations for the UNO Q's 8x13 LED matrix (brightness 0..7). Pure Python.

A frame is a list of 8 rows of 13 ints. `encode()` turns it into the 104-character string
('0'..'7', row by row) that the sketch asks for. Nothing here flashes faster than 3 times a second.
"""
import math

ROWS, COLS = 8, 13

DIGITS = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", ".#.", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
    "/": ["..#", "..#", ".#.", "#..", "#.."], "%": ["#.#", "..#", ".#.", "#..", "#.#"],
    "+": ["...", ".#.", "###", ".#.", "..."], "-": ["...", "...", "###", "...", "..."],
    "?": ["##.", "..#", ".#.", "...", ".#."],
}

ICONS = {
    # 5 wide x 7 tall, drawn in columns 0..4 (column 5 stays empty before the number)
    "signal": ["....#", "....#", "..#.#", "..#.#", "#.#.#", "#.#.#", "....."],
    "person": [".###.", ".###.", ".....", ".###.", "#####", "#####", "....."],
    "tick": [".....", "....#", "...#.", "#.#..", ".#...", ".....", "....."],
    "page": ["####.", "#...#", "#.#.#", "#...#", "#.#.#", "#...#", "#####"],
}

KANGAROO = [  # facing right, 6 x 7
    "....#.",
    "...###",
    "...##.",
    "..###.",
    "#####.",
    "#..#..",
    "...##.",
]

SAD = [".#####.", "#.....#", "#.#.#.#", "#.....#", "#..#..#", "#.#.#.#", ".#####."]


def blank(v=0):
    return [[v] * COLS for _ in range(ROWS)]


def encode(frame):
    return "".join(str(max(0, min(7, int(v)))) for row in frame for v in row)


def put(frame, r, c, v):
    if 0 <= r < ROWS and 0 <= c < COLS:
        frame[r][c] = max(frame[r][c], v)


def sprite(frame, rows, r0, c0, v=7):
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if ch == "#":
                put(frame, r0 + r, c0 + c, v)


def text(frame, s, c0, r0=1, v=7):
    """3x5 characters with one column between them."""
    for i, ch in enumerate(s):
        sprite(frame, DIGITS.get(ch, DIGITS["?"]), r0, c0 + i * 4, v)


def text_width(s):
    return len(s) * 4 - 1


def number(n):
    return "99" if n > 99 else str(max(0, int(n)))


def timer_bar(frame, t, duration, v=1):
    """Dim line on the bottom row that fills while a scene is shown."""
    for c in range(int(COLS * min(1, t / duration) + 0.5)):
        put(frame, 7, c, v)


# ------------------------------------------------------------------ scenes
# Each scene: render(t, data) -> frame, where t = seconds since the scene started.

def icon_and_number(icon, value, t, duration, pulse_rows=None):
    f = blank()
    level = 4 + round(3 * (0.5 + 0.5 * math.sin(t * 2.2)))   # slow breathing, 4..7
    sprite(f, ICONS[icon], 0, 0, level)
    s = number(value)
    text(f, s, COLS - text_width(s), 1)
    timer_bar(f, t, duration)
    return f


def wifi(t, d, duration):
    """Signal bars (devices on the board's Wi-Fi), lighting up one by one."""
    f = blank()
    step = int(t / 0.45) % 4                    # ~2 steps per second
    for i, col in enumerate((0, 2, 4)):
        v = 7 if i < step else 2
        for r, line in enumerate(ICONS["signal"]):
            if line[col] == "#":
                put(f, r, col, v)
    s = number(d.get("wifi_clients", 0))
    text(f, s, COLS - text_width(s), 1)
    timer_bar(f, t, duration)
    return f


def students(t, d, duration):
    return icon_and_number("person", d.get("online_students", 0), t, duration)


def submissions(t, d, duration):
    return icon_and_number("tick", d.get("submissions_today", 0), t, duration)


def topics(t, d, duration):
    """Class equaliser: one column per topic, height = average level (0..8)."""
    f = blank()
    avg = d.get("topic_avg") or []
    grow = min(1.0, t / 1.2)
    c0 = (COLS - len(avg)) // 2
    for i, a in enumerate(avg):
        h = round(max(0.0, min(8.0, a)) * grow)
        dim = 0 if i % 2 == 0 else 2                          # alternate columns so bars stay apart
        for k in range(h):
            put(f, ROWS - 1 - k, c0 + i, max(1, 2 + round(4 * k / 7) - dim))
        if h and grow >= 1:                                   # gentle shimmer on the peaks
            put(f, ROWS - h, c0 + i, 7 if int(t * 2 + i) % 3 == 0 else 6)
    return f


def accuracy(t, d, duration):
    f = blank()
    acc = d.get("accuracy_today")
    s = "--" if acc is None else number(round(acc * 100))
    s += "%"
    text(f, s, (COLS - text_width(s)) // 2, 1, 7)
    if acc is not None:
        fill = int(COLS * acc * min(1, t / 1.5) + 0.5)
        for c in range(fill):
            put(f, 7, c, 4)
    return f


def kangaroo(t, d, duration, speed=7.0):
    """The mascot hops across the matrix."""
    f = blank()
    x = -6 + (t * speed) % (COLS + 8)
    hop = abs(math.sin(t * speed / 4 * math.pi)) * 2      # one hop every 4 columns
    sprite(f, KANGAROO, round(1 - hop), round(x), 7)
    for c in range(COLS):                                   # the ground
        put(f, 7, c, 1)
    return f


def offline(t, d, duration):
    f = blank()
    v = 3 + round(4 * (0.5 + 0.5 * math.sin(t * 1.6)))     # slow breathing, never flashing
    sprite(f, SAD, 0, 3, v)
    return f


def booting(t, d, duration):
    """A bar that sweeps while the portal starts."""
    f = blank()
    x = int(t * 8) % (COLS + 4) - 2
    for c in range(COLS):
        put(f, 4, c, 1)
    for k in range(3):
        put(f, 4, x - k, 7 - 2 * k)
        put(f, 3, x - k, 3 - k)
    return f


# ------------------------------------------------------------------ one-off animations for events

def burst(t):
    """Expanding ring from the centre, ~0.8 s."""
    f = blank()
    radius = t * 9
    for r in range(ROWS):
        for c in range(COLS):
            dist = math.hypot((c - 6) * 0.8, r - 3.5)
            if abs(dist - radius) < 0.8:
                put(f, r, c, 7)
            elif abs(dist - radius + 1.2) < 0.6:
                put(f, r, c, 3)
    return f


def score(t, correct, total):
    f = blank()
    s = f"{number(correct)}/{number(total)}"
    text(f, s, (COLS - text_width(s)) // 2, 1, 7)
    acc = correct / total if total else 0
    for c in range(int(COLS * acc * min(1, t / 1.0) + 0.5)):
        put(f, 7, c, 5)
    if total and correct == total:                       # perfect: twinkling stars in the corners
        for i, (r, c) in enumerate([(0, 0), (0, 12), (6, 0), (6, 12)]):
            put(f, r, c, 7 if int(t * 2.5 + i) % 2 else 2)
    return f


def plus_icon(icon):
    def render(t):
        f = blank()
        sprite(f, ICONS[icon], 0, 0, 7)
        v = 4 + round(3 * (0.5 + 0.5 * math.sin(t * 5)))
        text(f, "+1", 6, 1, v)
        return f
    return render


def event_animation(ev):
    """List of (render(t), seconds) for an event coming from the portal."""
    kind = ev.get("kind")
    if kind == "submit":
        c, n = ev.get("correct", 0), ev.get("total", 0)
        return [(burst, 0.8), (lambda t: score(t, c, n), 3.0)]
    if kind == "login" and ev.get("role") == "student":
        return [(lambda t: kangaroo(t, {}, 0, speed=10), 2.0)]
    if kind == "student":
        return [(plus_icon("person"), 2.0)]
    if kind == "problem":
        return [(plus_icon("page"), 2.0)]
    return []


ROTATION = [(wifi, 5), (students, 5), (submissions, 5), (topics, 6), (accuracy, 4), (kangaroo, 4)]
