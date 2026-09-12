# Hugging Face post

Written for huggingface.co/posts, which caps a post at about 2,000 characters. The claims about
what does not exist (no mms-tts-bel, no Piper or Kokoro Belarusian voice) are the reason this
project exists, so they are worth re-checking here whenever the post is reused.

---

**There is no small, open, natural Belarusian voice. Not in Meta MMS, not in Piper, not in Kokoro.**

MMS has `mms-tts-ukr` and `mms-tts-rus` — no `mms-tts-bel`. Piper's collection has none. Kokoro has none. For a language with millions of speakers, the open TTS ecosystem simply skips it.

I found this out when a small humanoid robot I built said goodbye in Belarusian using an English voice reading a phonetic spelling. It sounded awful.

**What works today:** zero-shot voice cloning from a large multilingual model — [OmniVoice](https://github.com/k2-fsa/OmniVoice) (k2-fsa, Apache-2.0), which covers 600+ languages including Belarusian. The catch is that it carries the **accent of the reference recording** into everything it says, so the reference has to be a real Belarusian speaker with an exact transcript. I use a 6-second clip from Google's [FLEURS](https://huggingface.co/datasets/google/fleurs) Belarusian set (CC-BY-4.0).

It serves an OpenAI-compatible `/v1/audio/speech`:

```bash
uv run python server.py
curl -s 127.0.0.1:11810/v1/audio/speech \
  -H 'content-type: application/json' \
  -d '{"input": "Дзякуй! Да сустрэчы!"}' -o out.wav
```

**Honest about speed:** on a 16-thread CPU a 2-second sentence takes about a minute the first time. Every sentence is cached on disk, so repeats are instant. That makes it genuinely useful for fixed phrases and prepared text, and useless for live conversation — which is exactly why the second half of the project is a small **Piper voice** (VITS, ONNX, real-time on a Raspberry Pi) trained on openly licensed Belarusian speech.

What I need most is an evaluation set — sentences covering stress, `ў`, soft consonants, numbers and names — and native speakers willing to judge naturalness by ear. A script can't score this.

Калі вы размаўляеце па-беларуску, я буду вельмі ўдзячны за дапамогу.

https://github.com/YauhenBichel/belarusian-tts
