"""Command line: read the options of one or more M3Kang images.

    python3 -m answer_zone data/images/lvl-0_2015_13_eng.png
    python3 -m answer_zone img1.png img2.png --json
    python3 -m answer_zone img.png --zone-out zone.png --debug-out debug.png
    python3 -m answer_zone img.png --strict      # exit code 2 if an option is missing

Exit code: 0 when every image has its five options (or without --strict), 2 when
--strict and at least one image has a letter without a text value.
"""
import argparse
import json
import sys

from . import extract, load_recognizer
from .extract import zone_image


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m answer_zone", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("images", nargs="+")
    p.add_argument("--json", action="store_true", help="one JSON object per image")
    p.add_argument("--backend", default="auto", choices=["auto", "onnx", "tesseract"])
    p.add_argument("--strict", action="store_true", help="exit 2 if any option is not available")
    p.add_argument("--zone-out", help="save the answer-zone crop (single image only)")
    p.add_argument("--debug-out", help="save the annotated picture (single image only)")
    a = p.parse_args(argv)
    rec = load_recognizer(a.backend)
    failed = 0
    for path in a.images:
        r = extract(path, recognizer=rec)
        failed += not r.ok
        if a.json:
            print(json.dumps({"image": path, **r.to_dict()}, ensure_ascii=False))
        else:
            print(f"{path}  ({r.seconds['total'] * 1000:.0f} ms)")
            for L, o in r.options.items():
                print(f"  {L}) ERROR: {r.problems[L]}" if L in r.problems else f"  {L}) {o.value}")
            for w in r.warnings:
                print(f"  warning: {w}")
        if len(a.images) == 1 and (a.zone_out or a.debug_out):
            from PIL import Image
            if a.zone_out and r.zone:
                Image.fromarray(zone_image(path, r)).save(a.zone_out)
            if a.debug_out:
                from .visualize import panel
                panel(path, r, path).save(a.debug_out)
    if a.strict and failed:
        print(f"{failed} image(s) without all five options", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
