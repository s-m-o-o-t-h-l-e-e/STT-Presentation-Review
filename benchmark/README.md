# Benchmark Data and Verification Scripts

This folder accompanies the paper *"An Integrated STT-Based Multimodal Pre-Screening System for Korean Oral Presentations with an Analytics-Fitness Benchmark of Five Speech-to-Text Engines"* (submitted to Applied Sciences, 2026).

## Contents

- `data/per_file_results.csv` — per-file, per-engine benchmark results on the 20-recording evaluation set (N = 20; a pipeline `AVERAGE` row, if present in raw exports, is excluded from all statistics). Columns: raw pipeline CER and alignment counts (substitution / deletion / insertion) and reference length. **Reference and hypothesis transcripts are not included**, in line with the source-corpus licensing (AIHub KconfSpeech terms); the corpus is available to researchers via AIHub.
- `scripts/verify_paper_stats.py` — recomputes every statistic reported in the paper (corrected-normalization CER per engine, Friedman/Wilcoxon/Holm tests, Kendall's W, filler preservation rate, error composition) and checks them against the published values. All 31 checks pass on the authors' systems.
- `scripts/compute_cer.py` — standalone CER computation used by the pipeline (corrected normalization: dual transcriptions resolved to orthographic forms, non-speech codes removed, lowercasing, whitespace removal, Hangul-and-alphanumeric filtering).

## Reproducing the paper's numbers

1. Obtain the KconfSpeech corpus (AIHub) and the audio files listed in `per_file_results.csv` if you wish to re-run transcription; otherwise start from the CSVs here.
2. Run `python scripts/verify_paper_stats.py` (see script header for expected data paths).
3. The script prints each paper value alongside the recomputed value; mapping to the paper: CER/FPR per engine → Table 2; fitness profile → Table 3; error composition → Table 4.

## Notes

- Engine outputs reflect the API versions available at experiment time; commercial engines are moving targets (see Section 7.3 of the paper).
- Audio files and corpus transcripts are not redistributed here owing to source licensing (professional voice recordings; AIHub corpus terms).
