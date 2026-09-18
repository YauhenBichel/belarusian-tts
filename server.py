"""Natural Belarusian text-to-speech behind an OpenAI-style endpoint.

    uv run python server.py                    # 127.0.0.1:11810, loopback only
    curl -s 127.0.0.1:11810/v1/audio/speech -H 'content-type: application/json' \
         -d '{"input": "Дзякуй! Да сустрэчы!"}' -o out.wav

POST /v1/audio/speech  {"input": "...", "response_format": "wav", "speed": 1.0}  -> audio/wav, 24 kHz mono
GET  /healthz          {"ok": true, "model": ..., "reference": ...}

Model: k2-fsa/OmniVoice (Apache-2.0), zero-shot voice cloning, 600+ languages including
Belarusian. It clones a *native Belarusian* reference speaker: OmniVoice carries the accent of the
reference's language into its output, so a reference in another language gives accented Belarusian.
Reference: ref/voice.wav + ref/voice.txt, a FLEURS Belarusian clip with its exact transcript
(CC-BY-4.0; ref/SOURCE.md).

Environment: BELARUSIAN_TTS_CACHE (default ~/.cache/belarusian-tts), synthesis cache on disk.
"""

import argparse
import hashlib
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).parent
REF_AUDIO, REF_TEXT = HERE / "ref" / "voice.wav", HERE / "ref" / "voice.txt"
MODEL_ID = "k2-fsa/OmniVoice"
RATE = 24000
MAX_CHARS = 1000


def cache_dir() -> Path:
    return Path(os.environ.get("BELARUSIAN_TTS_CACHE", Path.home() / ".cache" / "belarusian-tts"))


def cache_name(text: str, speed: float, num_step: int, ref_text: str) -> str:
    """Everything that changes the audio is in the key: text, speed, steps, reference."""
    return hashlib.sha256(f"{text}|{speed}|{num_step}|{ref_text}".encode()).hexdigest()[:24] + ".wav"


def to_wav(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.asarray(audio, np.float32), RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class Speaker:
    """OmniVoice cloning the reference voice; memory and disk cache (synthesis is slow on CPU)."""

    def __init__(self, ref_audio: Path, ref_text: str, num_step: int, generate=None):
        if generate is None:
            import torch
            from omnivoice import OmniVoice

            torch.set_num_threads(max(1, (torch.get_num_threads() or 8) // 2))
            t = time.monotonic()
            # A CPU takes about a minute per sentence, which is fine for a fixed phrase and far too slow to measure a
            # voice over an evaluation set. BELARUSIAN_TTS_DEVICE=cuda puts it on a GPU where there is one; the default
            # stays cpu so that nothing changes for someone running this on a laptop.
            device = os.environ.get("BELARUSIAN_TTS_DEVICE", "cpu")
            try:
                model = OmniVoice.from_pretrained(MODEL_ID, device_map=device,
                                                  dtype=torch.float32 if device == "cpu" else torch.float16)
            except Exception as exc:  # noqa: BLE001 - a missing or busy GPU must not stop the server
                if device == "cpu":
                    raise
                print(f"{device} unavailable ({type(exc).__name__}: {exc}); falling back to cpu", flush=True)
                device = "cpu"
                model = OmniVoice.from_pretrained(MODEL_ID, device_map="cpu", dtype=torch.float32)
            self.device = device
            self.load_s = round(time.monotonic() - t, 1)
            generate = lambda text, speed: model.generate(text=text, ref_audio=str(ref_audio), ref_text=ref_text,
                                                         num_step=num_step, speed=speed)[0]
        else:
            self.load_s, self.device = 0.0, "test"
        self.generate, self.ref_text, self.num_step = generate, ref_text, num_step
        self.cache: dict[tuple, bytes] = {}
        self.lock = threading.Lock()  # one synthesis at a time; the model is not re-entrant

    def wav(self, text: str, speed: float = 1.0) -> bytes:
        key = (text, speed)
        with self.lock:
            if key not in self.cache:
                cached = cache_dir() / cache_name(text, speed, self.num_step, self.ref_text)
                if cached.exists():
                    self.cache[key] = cached.read_bytes()
                else:
                    self.cache[key] = to_wav(self.generate(text, speed))
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_bytes(self.cache[key])
            return self.cache[key]


def reference() -> tuple[Path, str]:
    if not (REF_AUDIO.exists() and REF_TEXT.exists()):
        raise SystemExit(f"missing reference {REF_AUDIO} / {REF_TEXT} (see ref/SOURCE.md)")
    return REF_AUDIO, REF_TEXT.read_text().strip()


def parse_request(body: bytes) -> tuple[str, float]:
    """The OpenAI speech request, validated. Raises ValueError with a reason."""
    try:
        req = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}") from None
    if not isinstance(req, dict) or not isinstance(req.get("input"), str):
        raise ValueError("expected {\"input\": \"text\"}")
    text = req["input"].strip()
    if not text or len(text) > MAX_CHARS:
        raise ValueError(f"input must be 1-{MAX_CHARS} characters")
    if req.get("response_format", "wav") != "wav":
        raise ValueError("only response_format \"wav\" is supported")
    speed = req.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0.5 <= speed <= 2.0:
        raise ValueError("speed must be a number in 0.5-2.0")
    return text, float(speed)


def handler(speaker: Speaker, info: dict):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, json.dumps({"ok": True, **info}).encode(), "application/json")
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/v1/audio/speech":
                return self._send(404, b"not found", "text/plain")
            try:
                text, speed = parse_request(self.rfile.read(int(self.headers.get("content-length", 0))))
            except ValueError as e:
                return self._send(400, f"bad request: {e}".encode(), "text/plain")
            t = time.monotonic()
            wav = speaker.wav(text, speed)
            print(f"{time.strftime('%H:%M:%S')} {len(text)} chars -> {time.monotonic() - t:.1f} s", flush=True)
            self._send(200, wav, "audio/wav")

    return H


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=11810)
    p.add_argument("--num-step", type=int, default=32, help="diffusion steps (16 is faster)")
    args = p.parse_args()
    ref_audio, ref_text = reference()
    speaker = Speaker(ref_audio, ref_text, args.num_step)
    info = {"model": MODEL_ID, "reference": "FLEURS be_by dev 2411614122304034736 (CC-BY-4.0)", "ref_text": ref_text,
            "num_step": args.num_step, "load_s": speaker.load_s,
            "device": getattr(speaker, "device", "cpu")}
    srv = ThreadingHTTPServer((args.host, args.port), handler(speaker, info))
    print(f"belarusian-tts on http://{args.host}:{args.port} ({info})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
