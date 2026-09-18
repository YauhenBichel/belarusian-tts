#!/usr/bin/env python3
"""Measure this voice the only way that is not an opinion: say a fixed set of sentences, listen back with a
recogniser, and count the errors — against the same sentences read by people.

Round-trip word error rate is the standard objective measure for a synthetic voice, and the number only means
something next to a ceiling: the same recogniser on human recordings of the *same* sentences. Belarusian gives us
that for free, because FLEURS has both the text and human audio, and `belarusian-asr` scores 10.8 % WER on it. A
voice that round-trips at 12 % is doing well; one at 40 % is mangling words, and the per-group table says which
words.

This does not measure naturalness — no automatic metric does. It measures intelligibility, and it catches the
failures that matter most in Belarusian: wrong stress turning one word into another, numbers and abbreviations read
as letters, foreign terms, `ў`, soft consonants and long consonants. Naturalness is judged by ear on the same
audio; `--listening-set` writes a folder for that.

Usage:
  roundtrip.py --sentences eval/sentences.tsv --out eval/runs/2026-09-17 [--endpoint http://127.0.0.1:11810]
               [--speed 1.0] [--label "num_step=32"] [--human eval/human.tsv] [--listening-set]
  roundtrip.py --report eval/runs/2026-09-17          # re-print the table from a finished run

Needs a recogniser: `pip install belarusian-asr`, or an ONNX NeMo model in BE_ASR_MODEL
(e.g. models/stt_be_fastconformer_hybrid_large_pc_onnx) with `onnx_asr` importable.
Exit: 0 measured, 1 could not measure.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

APOS = {ord("’"): "'", ord("ʼ"): "'"}
STRESS = "́̀"


def norm(text: str) -> str:
    """Lower case, no stress marks, no punctuation: what both sides are scored on, so spelling of punctuation
    cannot count as a mistake (the same normaliser idea Whisper's own benchmark uses)."""
    text = unicodedata.normalize("NFD", (text or "").lower()).translate(APOS)
    text = "".join(c for c in text if c not in STRESS)
    text = unicodedata.normalize("NFC", text)
    return " ".join(re.sub(r"[^\w' ]+", " ", text).split())


def edits(a: list, b: list) -> int:
    """Levenshtein distance, iterative, two rows."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def score(reference: str, hypothesis: str) -> dict:
    ref, hyp = norm(reference), norm(hypothesis)
    words, chars = ref.split(), list(ref)
    return {"wer": round(edits(words, hyp.split()) / max(len(words), 1), 4),
            "cer": round(edits(chars, list(hyp)) / max(len(chars), 1), 4),
            "words": len(words), "hyp": hyp}


def read_audio(path: Path):
    """-> (mono float32 samples, sample rate), whatever the WAV encoding.

    onnx_asr's own reader takes PCM only, and FLEURS ships 32-bit float WAVs: on 2026-09-18 every human recording
    came back as an error and the human ceiling read 100 % WER. soundfile reads both.
    """
    import numpy as np
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return np.ascontiguousarray(audio.mean(axis=1)), rate


def _recognise_file(model, path: Path) -> str:
    samples, rate = read_audio(path)
    return model.recognize(samples, sample_rate=rate)


class Recogniser:
    """belarusian-asr if it is installed, else the ONNX model in BE_ASR_MODEL."""

    def __init__(self) -> None:
        self.name, self._recognise = "", None
        try:
            from belarusian_asr import load_model  # type: ignore
            self.name, self._model = "belarusian-asr", load_model()
            self._recognise = lambda path: self._model.recognize(path)
            return
        except Exception:  # noqa: BLE001 - fall through to the raw ONNX model
            pass
        model_dir = os.environ.get("BE_ASR_MODEL", "")
        if not model_dir or not Path(model_dir).exists():
            raise RuntimeError("no recogniser: pip install belarusian-asr, or set BE_ASR_MODEL to an ONNX NeMo model")
        import onnx_asr  # type: ignore
        self.name = f"onnx_asr {Path(model_dir).name}"
        model = onnx_asr.load_model("nemo-conformer-ctc", model_dir)
        self._recognise = lambda path: _recognise_file(model, path)

    def __call__(self, path: Path) -> str | None:
        """The transcript, or None when the clip could not be recognised — never an error message dressed up as
        a transcript, which would be scored as a very wrong sentence."""
        try:
            return self._recognise(path) or ""
        except Exception as exc:  # noqa: BLE001 - one bad clip must not stop a run
            print(f"{path.name}: not recognised ({type(exc).__name__}: {exc})", file=sys.stderr, flush=True)
            return None


def synthesise(endpoint: str, text: str, out: Path, speed: float, timeout: float) -> tuple[bool, str]:
    body = json.dumps({"input": text, "response_format": "wav", "speed": speed}).encode()
    req = urllib.request.Request(endpoint.rstrip("/") + "/v1/audio/speech", data=body,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out.write_bytes(r.read())
        return True, ""
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def read_sentences(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader((l for l in fh if not l.startswith("#")), delimiter="\t"):
            if row.get("text", "").strip():
                # `text` is what the voice is given; `reference` is what it should say, when the two differ
                # (digits, abbreviations, formulas). Scoring «а 7:45» against «а сёмай сорак пяць» as wrong would
                # measure the test, not the voice.
                rows.append({"id": row["id"].strip(), "group": (row.get("group") or "other").strip(),
                             "text": row["text"].strip(), "audio": (row.get("audio") or "").strip(),
                             "reference": (row.get("reference") or "").strip() or row["text"].strip()})
    return rows


def table(results: list[dict], title: str) -> list[str]:
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(r["group"], []).append(r)
    lines = [f"### {title}", "", "| group | sentences | WER | CER |", "|---|---|---|---|"]
    for group, rows in sorted(groups.items(), key=lambda kv: -statistics.fmean([r["wer"] for r in kv[1]])):
        lines.append(f"| {group} | {len(rows)} | {statistics.fmean([r['wer'] for r in rows]):.1%} | "
                     f"{statistics.fmean([r['cer'] for r in rows]):.1%} |")
    lines.append(f"| **all** | {len(results)} | **{statistics.fmean([r['wer'] for r in results]):.1%}** | "
                 f"**{statistics.fmean([r['cer'] for r in results]):.1%}** |")
    return lines + [""]


def report(run_dir: Path) -> int:
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    lines = [f"# Round-trip evaluation — {data['label']}", "",
             f"{data['at']} · recogniser: {data['recogniser']} · endpoint {data['endpoint']} · "
             f"speed {data['speed']} · {data['seconds_total']:.0f} s for {len(data['synthetic'])} sentences", "",
             "Word error rate of this voice read back by a recogniser. Lower is better; the human row is the ceiling "
             "— the same recogniser on people reading the same sentences.", ""]
    if data.get("not_recognised"):
        lines += [f"**{len(data['not_recognised'])} clip(s) could not be recognised and are left out, not scored:** "
                  + ", ".join(data["not_recognised"]), ""]
    lines += table(data["synthetic"], "This voice")
    if data.get("human"):
        lines += table(data["human"], "Human recordings of the same sentences (ceiling)")
        # Only the sentences that exist in both: comparing the voice on all 50 with people on 25 would mix the
        # hard hand-written groups into one side only.
        both = {r["id"] for r in data["human"]}
        voice = [r["wer"] for r in data["synthetic"] if r["id"] in both]
        people = [r["wer"] for r in data["human"]]
        if voice:
            gap = statistics.fmean(voice) - statistics.fmean(people)
            lines += [f"**On the {len(voice)} sentences read by both: voice {statistics.fmean(voice):.1%} WER, "
                      f"people {statistics.fmean(people):.1%} — gap {gap:+.1%}.**", ""]
    worst = sorted(data["synthetic"], key=lambda r: -r["wer"])[:12]
    lines += ["### Worst sentences", "", "| WER | group | said | heard |", "|---|---|---|---|"]
    lines += [f"| {r['wer']:.0%} | {r['group']} | {r['text']} | {r['hyp']} |" for r in worst]
    out = run_dir / "REPORT.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten to {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sentences", default="eval/sentences.tsv")
    p.add_argument("--out", help="run directory (default eval/runs/DATE)")
    p.add_argument("--endpoint", default=os.environ.get("BELARUSIAN_TTS_URL", "http://127.0.0.1:11810"))
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--label", default="", help="what is being tested, e.g. 'owner reference, num_step=32'")
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--listening-set", action="store_true", help="also copy the clips for a human to rate")
    p.add_argument("--report", help="just re-print the table of a finished run")
    a = p.parse_args(argv)
    if a.report:
        return report(Path(a.report))

    sentences = read_sentences(Path(a.sentences))
    if a.limit:
        sentences = sentences[:a.limit]
    if not sentences:
        print(f"no sentences in {a.sentences}", file=sys.stderr)
        return 1
    run_dir = Path(a.out or f"eval/runs/{time.strftime('%Y-%m-%d')}")
    (run_dir / "audio").mkdir(parents=True, exist_ok=True)
    try:
        asr = Recogniser()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    started, synthetic, human, failed = time.monotonic(), [], [], []
    for i, s in enumerate(sentences, 1):
        wav = run_dir / "audio" / f"{s['id']}.wav"
        ok, err = synthesise(a.endpoint, s["text"], wav, a.speed, a.timeout)
        if not ok:
            print(f"{s['id']}: synthesis failed ({err})", file=sys.stderr)
            continue
        heard = asr(wav)
        if heard is None:
            failed.append(s["id"])
            continue
        row = dict(s, **score(s["reference"], heard))
        synthetic.append(row)
        print(f"{i}/{len(sentences)} {s['id']} [{s['group']}] WER {row['wer']:.0%}  heard: {row['hyp'][:60]}",
              flush=True)
        if s["audio"] and Path(s["audio"]).exists():
            heard = asr(Path(s["audio"]))
            if heard is None:
                failed.append(s["id"] + " (human)")
            else:
                human.append(dict(s, **score(s["reference"], heard)))
    if not synthetic:
        print("nothing was synthesised; is the server running?", file=sys.stderr)
        return 1

    data = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "label": a.label or "belarusian-tts",
            "endpoint": a.endpoint, "speed": a.speed, "recogniser": asr.name,
            "seconds_total": round(time.monotonic() - started, 1), "synthetic": synthetic, "human": human,
            "not_recognised": failed}
    (run_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.listening_set:
        listen = run_dir / "listening"
        listen.mkdir(exist_ok=True)
        for r in synthetic:
            shutil.copy(run_dir / "audio" / f"{r['id']}.wav", listen / f"{r['id']}.wav")
        (listen / "ratings.tsv").write_text(
            "clip\tnatural_1_5\tstress_ok_yes_no\tnote\n" + "".join(f"{r['id']}\t\t\t\n" for r in synthetic),
            encoding="utf-8")
    return report(run_dir)


if __name__ == "__main__":
    sys.exit(main())
