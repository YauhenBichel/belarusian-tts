# Contributing · Як дапамагчы

The most valuable help is a **native Belarusian ear**: listen to generated sentences and say what
sounds wrong (stress, `ў`, soft consonants, rhythm). Open an issue with the sentence, what you heard
and what it should be.

Code changes:

1. One change per pull request, with a test for the behaviour it changes (`uv run python -m pytest`).
   The tests use a fake voice, so they run in seconds without the model.
2. Keep the endpoint OpenAI-compatible; document any new request field in the README.
3. New reference voices or training data must have a licence that allows redistribution, recorded
   with attribution next to the file.

Найбольш каштоўная дапамога — слых носьбіта мовы: паслухайце сказы і напішыце, што гучыць не так.
