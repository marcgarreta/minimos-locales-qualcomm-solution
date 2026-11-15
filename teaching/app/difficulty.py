"""General difficulty: the position of a problem on the whole Kangaroo ladder.

The number after the last "_" in an M3Kang id is the question number in its exam, and the
exams are ordered from easy to hard. Levels 0-1 have 24 questions and levels 2-7 have 30, so
the general difficulty stacks them:

    general = (questions of all lower levels) + question number
    level 0, question 8  ->   8
    level 1, question 3  ->  24 + 3 = 27
    level 2, question 1  ->  48 + 1 = 49   ...  up to 228

"Harder" and "easier" mean a few steps up or down this ladder: inside the same level, and only
at the top (or bottom) of a level do they reach into the next (or previous) one.
"""

DEFAULT_SIZE = 30


def question_number(pid):
    tail = str(pid).rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else None


def ladder(level_num_pairs, levels=8):
    """Offsets per level from the (level, question number) pairs in the bank."""
    sizes = {}
    for lv, num in level_num_pairs:
        if num:
            sizes[lv] = max(sizes.get(lv, 0), num)
    offsets, acc = {}, 0
    for lv in range(levels):
        offsets[lv] = acc
        acc += sizes.get(lv, DEFAULT_SIZE)
    return {"offsets": offsets, "sizes": {lv: sizes.get(lv, DEFAULT_SIZE) for lv in range(levels)}, "total": acc}


def general(lad, level, num):
    size = lad["sizes"].get(level, DEFAULT_SIZE)
    num = num if num else (size + 1) // 2          # problems without a number sit mid-level
    return lad["offsets"].get(level, 0) + min(max(num, 1), size)


def neighbours(items, g, level, direction, step=4, need=1):
    """Ids from `items` [(id, g, level)] a little harder (+1) or easier (-1) than g.
    The same level comes first; the next (or previous) level only fills what is missing,
    which happens at the top (or bottom) questions of a level."""
    ids = window([(i, x) for i, x, lv in items if lv == level], g, direction, step, need)
    if len(ids) < need:
        ids += window([(i, x) for i, x, lv in items if lv != level], g, direction, step, need - len(ids))
    return ids


def window(items, g, direction, step=4, need=1):
    """Ids from `items` [(id, g)] just above (direction=+1) or below (-1) difficulty g.
    Starts with `step` places and widens until at least `need` are found."""
    for width in (step, step * 2, step * 4, step * 8, 10 ** 6):
        if direction > 0:
            ids = [i for i, x in items if g < x <= g + width]
        else:
            ids = [i for i, x in items if g - width <= x < g]
        if len(ids) >= need:
            return ids
    return ids
