"""The evaluation harness: scoring, the spoken-form reference, float WAVs, and never scoring an error as speech."""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import roundtrip  # noqa: E402


def test_punctuation_case_and_stress_marks_are_not_errors():
    assert roundtrip.score("Дзя́куй! Да сустрэчы.", "дзякуй да сустрэчы")["wer"] == 0.0


def test_one_wrong_word_in_four():
    assert roundtrip.score("гэта мука з пшаніцы", "гэта мука з пшаніцай")["wer"] == 0.25


def test_numbers_are_scored_against_their_spoken_form(tmp_path):
    tsv = tmp_path / "s.tsv"
    tsv.write_text("id\tgroup\ttext\taudio\treference\n"
                   "n1\tnumbers\tАўтобус а 7:45.\t\tАўтобус а сёмай сорак пяць.\n"
                   "p1\tplain\tДобры вечар.\t\t\n", encoding="utf-8")
    rows = {r["id"]: r for r in roundtrip.read_sentences(tsv)}
    assert rows["n1"]["text"] == "Аўтобус а 7:45."
    assert rows["n1"]["reference"] == "Аўтобус а сёмай сорак пяць."
    assert rows["p1"]["reference"] == "Добры вечар."


def test_float_wavs_are_read(tmp_path):
    """FLEURS ships IEEE-float WAVs, which onnx_asr's own reader refuses."""
    wav = tmp_path / "float.wav"
    sf.write(wav, np.zeros((1600, 2), np.float32), 16000, subtype="FLOAT")
    samples, rate = roundtrip.read_audio(wav)
    assert rate == 16000 and samples.ndim == 1 and samples.dtype == np.float32


def test_an_unrecognised_clip_is_none_not_a_transcript(tmp_path, capsys):
    asr = roundtrip.Recogniser.__new__(roundtrip.Recogniser)
    asr.name = "broken"

    def boom(path):
        raise ValueError("unknown format: 3")

    asr._recognise = boom
    assert asr(tmp_path / "x.wav") is None
    assert "not recognised" in capsys.readouterr().err
