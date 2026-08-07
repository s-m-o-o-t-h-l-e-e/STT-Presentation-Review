# STT CER Benchmark Package

This folder contains the public benchmark artifacts referenced for paper review.

## Contents

- `results/stt_model_cer_by_audio_file.csv`  
  Per-audio CER values by STT engine. Transcript text and audio files are intentionally excluded.
- `results/stt_model_average_cer_summary.csv`  
  Average CER by STT engine.
- `verify_cer_summary.py`  
  Recomputes average CER values from the per-audio CSV and checks them against the summary CSV.
- `UPLOAD_GUIDE.md`  
  Short checklist for uploading this folder to the repository root.

## Reproducibility Note

The benchmark results were generated on `2026-07-22 17:29:04 +0900` from 20 audio samples. The STT engines invoked by the benchmark script were CLOVA Speech recognizer upload API, Azure Speech conversation recognition v1 (`ko-KR`), OpenAI Whisper API model `whisper-1`, Google Speech-to-Text v2 model `latest_long` when service-account credentials were used, and AssemblyAI v2 transcript API.

## Verify

Run from the repository root:

```bash
python benchmark/verify_cer_summary.py
```

Expected output should mark every engine column as `OK`.
