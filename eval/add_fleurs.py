#!/usr/bin/env python3
"""Add FLEURS sentences with their human recordings, so the voice has a ceiling to be measured against.

A round-trip word error rate on its own says little: a recogniser makes mistakes on people too. FLEURS be_by
(CC-BY-4.0) gives the same sentence as text *and* as a human recording, so the same recogniser scores both and the
gap is the voice's. This picks short, digit-free sentences (long ones mostly measure the recogniser) and appends
them to an evaluation file as group `fleurs`, with the path to the human wav.

Usage: add_fleurs.py --tsv PATH_TO_FLEURS.tsv --audio-dir DIR [--out eval/sentences-with-human.tsv] [--n 25]
       The FLEURS tsv is id, wav name, text, normalised text, …  (as shipped by the dataset's own export).
Exit: 0 written, 1 nothing usable.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--tsv", required=True)
    p.add_argument("--audio-dir", required=True)
    p.add_argument("--base", default="eval/sentences.tsv", help="the hand-written set to extend")
    p.add_argument("--out", default="eval/sentences-with-human.tsv")
    p.add_argument("--n", type=int, default=25)
    p.add_argument("--max-words", type=int, default=16)
    a = p.parse_args(argv)

    seen, rows = set(), []
    for line in Path(a.tsv).read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        fid, wav, text = parts[0], parts[1], parts[2].strip()
        if fid in seen or re.search(r"\d", text) or len(text.split()) > a.max_words:
            continue
        path = Path(a.audio_dir) / wav
        if not path.exists():
            continue
        seen.add(fid)
        rows.append(f"f{fid}\tfleurs\t{text}\t{path}")
        if len(rows) >= a.n:
            break
    if not rows:
        print("no usable FLEURS sentences found", file=sys.stderr)
        return 1
    base = Path(a.base).read_text(encoding="utf-8").rstrip("\n")
    Path(a.out).write_text(base + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"{a.out}: {len(rows)} FLEURS sentences with human audio added")
    return 0


if __name__ == "__main__":
    sys.exit(main())
