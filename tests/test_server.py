"""The HTTP contract and the cache, with a fake voice (the real model is 1.2 GB and slow on CPU)."""

import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
import soundfile as sf

import server


@pytest.fixture
def running(tmp_path, monkeypatch):
    monkeypatch.setenv("BELARUSIAN_TTS_CACHE", str(tmp_path / "cache"))
    calls = []

    def generate(text, speed):
        calls.append((text, speed))
        return 0.1 * np.sin(np.linspace(0, 2 * np.pi * 220, int(server.RATE * 0.5)))

    speaker = server.Speaker(server.REF_AUDIO, "reference text", num_step=32, generate=generate)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.handler(speaker, {"model": "fake"}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", calls, speaker
    srv.shutdown()


def post(url, payload):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(url + "/v1/audio/speech", data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers["content-type"], r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers["content-type"], e.read()


def test_speech_is_a_24khz_mono_wav(running):
    url, calls, _ = running
    status, ctype, body = post(url, {"input": "  Дзякуй, Яўген!  ", "response_format": "wav"})
    audio, rate = sf.read(io.BytesIO(body))
    assert (status, ctype, rate, audio.ndim) == (200, "audio/wav", 24000, 1)
    assert calls == [("Дзякуй, Яўген!", 1.0)]   # trimmed text reached the model


def test_repeats_come_from_the_cache_and_survive_a_restart(running, tmp_path):
    url, calls, speaker = running
    first = post(url, {"input": "Добры дзень"})[2]
    assert post(url, {"input": "Добры дзень"})[2] == first and len(calls) == 1
    speaker.cache.clear()                              # a restarted server: disk cache only
    assert post(url, {"input": "Добры дзень"})[2] == first and len(calls) == 1
    assert post(url, {"input": "Добры дзень", "speed": 1.2})[0] == 200 and len(calls) == 2   # speed is in the key


@pytest.mark.parametrize("payload, reason", [
    (b"not json", "not JSON"),
    ({"text": "wrong field"}, "expected"),
    ({"input": "   "}, "1-1000"),
    ({"input": "x" * 1001}, "1-1000"),
    ({"input": "ok", "response_format": "mp3"}, "wav"),
    ({"input": "ok", "speed": 5}, "speed"),
    ({"input": "ok", "speed": True}, "speed"),
])
def test_bad_requests_are_400_with_a_reason_and_never_reach_the_model(running, payload, reason):
    url, calls, _ = running
    status, _, body = post(url, payload)
    assert status == 400 and reason in body.decode() and calls == []


def test_health_and_unknown_paths(running):
    url, _, _ = running
    with urllib.request.urlopen(url + "/healthz", timeout=5) as r:
        assert json.load(r) == {"ok": True, "model": "fake"}
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url + "/nope", timeout=5)


def test_the_reference_clip_and_its_transcript_are_present():
    audio, text = server.reference()
    data, rate = sf.read(audio)
    assert rate == 16000 and 5.0 < len(data) / rate < 7.0
    assert text.startswith("На некаторых фестывалях")
