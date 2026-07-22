# STT Model Evaluation

STT 모델별 CER을 비교하기 위한 실험 폴더입니다.  
회의 음성은 정답 전사문이 있어서 CER 계산에 사용하고, 성우 음성은 정답 전사문이 아직 없어서 후보 목록만 따로 남깁니다.

## 파일 구성

```text
evaluation/
  create_evaluation_manifest.py
  run_stt_model_cer_benchmark.py
  verify_cer_summary.py

  speech_audio_reference_manifest.csv
  speech_audio_reference_manifest.template.csv
  voice_actor_audio_missing_references.csv

  results/
    stt_model_cer_by_audio_file.csv
    stt_model_average_cer_summary.csv
    stt_model_transcripts_and_cer_details.csv
```

## 각 파일 역할

- `create_evaluation_manifest.py`
  - 회의 음성 라벨 TXT와 WAV를 매칭해서 평가 목록을 만듭니다.
  - `--seed`를 사용해서 랜덤 샘플을 재현 가능하게 뽑습니다.
- `run_stt_model_cer_benchmark.py`
  - 5개 STT 모델에 실제 음성을 넣고 전사 결과를 받습니다.
  - 정답 전사문과 비교해서 파일별 CER을 계산합니다.
- `verify_cer_summary.py`
  - 파일별 CER 평균과 summary CSV 평균이 맞는지 확인합니다.
- `speech_audio_reference_manifest.csv`
  - 실제 CER 계산에 들어가는 음성 파일과 정답 전사문 목록입니다.
- `voice_actor_audio_missing_references.csv`
  - 성우 음성 중 정답 전사문이 없는 파일 목록입니다.

## 평가 데이터 만들기

```powershell
python evaluation\create_evaluation_manifest.py `
  --speech-root "C:\Users\cdoai\OneDrive\문서\stt project\evaluation\speech_data" `
  --voice-root "C:\Users\cdoai\OneDrive\문서\stt project\evaluation\voice actor_data" `
  --limit 20 `
  --voice-limit 20 `
  --seed 42
```

회의 음성은 `라벨링데이터`의 TXT와 `원천데이터`의 WAV가 1:1로 맞는 파일만 후보로 잡습니다.  
그 후보를 seed 기준으로 섞고 `--limit` 개수만큼 사용합니다.

## 모델 비교 실행

```powershell
python evaluation\run_stt_model_cer_benchmark.py --engines clova,azure,whisper,google,assemblyai
```

실행 시 API 키는 `.env.private`를 먼저 읽습니다.  
`.env.private`가 없으면 `.env`를 읽습니다.

## 비교 모델

- Naver CLOVA Speech
- Azure Speech
- OpenAI Whisper
- Google Speech-to-Text v2
- AssemblyAI

## 결과 파일

- `results/stt_model_cer_by_audio_file.csv`
  - 오디오 파일별, 모델별 CER 원본표입니다.
- `results/stt_model_average_cer_summary.csv`
  - 모델별 평균 CER 요약입니다.
- `results/stt_model_transcripts_and_cer_details.csv`
  - 정답 전사문, 모델 전사문, S/D/I 계산값이 들어간 상세 로그입니다.

## 평균 검증

```powershell
python evaluation\verify_cer_summary.py
```

현재 검증 기준은 파일별 CER을 다시 평균 내서 summary에 적힌 값과 맞는지 보는 방식입니다.

## CER 계산

```text
CER = (Substitution + Deletion + Insertion) / Reference Characters * 100
```

공백과 문장부호는 제거하고 한글/영문/숫자만 남긴 뒤 문자 단위로 비교합니다.
