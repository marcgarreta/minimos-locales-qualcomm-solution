"""How far a student is in each topic.

Each (student, topic) has an ability `theta` on the 0..LEVELS scale (Elo / Rasch style).
A problem of level L has difficulty L + 0.5. After each answer:

    expected = 1 / (1 + exp(-SLOPE * (theta - difficulty)))
    theta   += K(n) * (correct - expected)

So the current level is not the hardest problem solved: one lucky right answer far above
your level moves theta only a little, and mistakes on easy problems pull it down.
Shown level = floor(theta) (0-based, the UI adds 1); the fraction is the progress bar.
"""
import math

SLOPE = 1.6
LEVELS = 8


def k_factor(n):
    return max(0.3, 0.9 / math.sqrt(1 + n / 3))


def expected(theta, level):
    return 1 / (1 + math.exp(-SLOPE * (theta - (level + 0.5))))


def update(theta, n, level, correct):
    theta += k_factor(n) * ((1.0 if correct else 0.0) - expected(theta, level))
    return min(max(theta, 0.0), LEVELS - 0.001), n + 1


def initial_theta(start_level):
    return start_level + 0.5


def describe(theta):
    lv = int(theta)
    return {"theta": round(theta, 3), "level": lv, "progress": round(theta - lv, 3)}
