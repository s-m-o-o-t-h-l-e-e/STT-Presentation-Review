# Benchmark Upload Guide

Upload the entire `benchmark/` folder to the repository root:

```text
STT-Presentation-Review/
  benchmark/
    README.md
    UPLOAD_GUIDE.md
    verify_cer_summary.py
    results/
      stt_model_cer_by_audio_file.csv
      stt_model_average_cer_summary.csv
```

One thing to check before upload: do not include transcript text, audio files, `.env`, `.env.private`, or service-account JSON files. This package contains numeric CER values only.
