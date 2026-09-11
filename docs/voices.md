# Choosing a reference voice

OmniVoice clones whoever speaks in `ref/voice.wav`, and it copies their **accent**. So:

1. **The reference must be Belarusian speech.** An English or Russian reference gives English- or
   Russian-accented Belarusian.
2. **The transcript must be exact** (`ref/voice.txt`): the model aligns the reference audio with this
   text. A wrong transcript degrades the clone. Do not rely on Whisper to write it — on our setup Whisper
   translated Belarusian speech into English instead of transcribing it.
3. **5–10 seconds, one speaker, clean, no music**, ideally without digits in the text.
4. **A licence that allows it**, recorded in `ref/SOURCE.md` with attribution.

The default clip is FLEURS `be_by` dev `2411614122304034736` (female, 6.0 s, CC-BY-4.0). FLEURS ships a
transcript per clip, which is why it was chosen. Mozilla Common Voice Belarusian (CC0) is another good
source of clips with transcripts.

To switch: replace `ref/voice.wav` and `ref/voice.txt`, update `ref/SOURCE.md`, restart the server.
The disk cache key includes the transcript, so old audio is not reused for the new voice.
