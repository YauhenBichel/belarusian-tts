# Reference voice

`voice.wav` (16 kHz, 6.0 s, female speaker) and `voice.txt` (its transcript) are clip
`2411614122304034736.wav` from the Belarusian (`be_by`) **dev** split of **FLEURS**
(Conneau et al., 2022; `google/fleurs` on Hugging Face), licensed **CC-BY-4.0**.

Why this clip: OmniVoice carries the accent of the reference's language into the voice it
generates, so natural Belarusian needs a native Belarusian reference with an exact transcript.
FLEURS gives both. Chosen on 11 September 2026 among female speakers of 5–9 s, preferring a
transcript without digits; a Whisper (large-v3-turbo) setup translated it accurately into English
("At some festivals, families with small children can use special camping…"), so it is clearly
spoken (that setup did not honour the Belarusian language hint, so it could not score transcripts).

Attribution: FLEURS — Conneau, Ma, Khanuja, Zhang, Axelrod, Dalmia, Riesa, Rivera, Bapna,
"FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech", 2022;
https://huggingface.co/datasets/google/fleurs, CC-BY-4.0. The clip is unmodified.

Transcript: «На некаторых фестывалях сем'і з маленькімі дзецьмі могуць карыстацца
спецыяльнымі кемпінгамі.» (At some festivals, families with small children can use special
campsites.)
