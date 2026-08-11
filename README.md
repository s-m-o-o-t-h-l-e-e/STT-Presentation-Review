# STT Presentation Review

발표 음성과 발표자료를 함께 분석해서 발표 속도, 추임새, 문장별 타임라인, 자료 반영률, 예상 질문, 개선 피드백을 확인하는 발표 평가 프로젝트입니다.

웹에서는 발표 음성 파일을 업로드하거나 실시간 발표 연습을 진행할 수 있고, PPT/PDF 자료를 같이 올리면 음성 전사 내용과 발표자료의 일치율도 비교합니다. STT 모델 비교 실험은 `evaluation/`과 `benchmark/` 폴더에서 따로 관리합니다.

## 주요 기능

- 발표 음성 업로드 후 Naver CLOVA Speech 기반 전사
- 문장별 timestamp, 공백 시간, 화자 정보 정리
- WPM 기준 발화 속도 계산
- 추임새 단어, 어휘 개선, 발표 흐름 분석
- PPT/PDF 발표자료 텍스트 추출 및 음성 전사와 일치율 비교
- 발표 연습 화면에서 자료 페이지별 체류 시간과 실시간 전사 기록
- Claude API를 활용한 예상 질문, 문제점, 보완 사항, 종합 의견 생성
- 분석 결과 PDF 리포트 다운로드
- STT 엔진별 CER 비교 실험

## 실행 방법

```powershell
pip install -r requirements.txt
python server.py
```

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8502
```

## 환경 변수

실제 실행 키는 `.env`에 넣습니다. `.env`와 `.env.private`는 GitHub에 올리지 않습니다.

```text
CLOVA_SPEECH_SECRET_KEY
CLOVA_SPEECH_INVOKE_URL
CLAUDE_API_KEY
CLAUDE_MODEL
```

STT 모델 비교 실험에는 별도 키가 필요합니다.

```text
AZURE_SPEECH_KEY
OPENAI_API_KEY
GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_CLOUD_PROJECT
ASSEMBLYAI_API_KEY
```

필요한 항목 예시는 `.env.example`을 참고하면 됩니다.

## 폴더 구조

```text
stt_project/
  server.py                  # 로컬 웹 서버
  index.html                 # 웹 화면
  app.js                     # 화면 동작과 API 호출
  styles.css                 # 웹 UI 스타일
  requirements.txt
  .env.example

  presentation_review/
    config/                  # 환경 설정
    speech_to_text/           # CLOVA Speech 연동
    speech_analysis/          # WPM, 추임새, 타임라인 계산
    materials/                # PPT/PDF 텍스트 추출과 자료 매칭
    llm/                      # Claude 평가 요청
    reports/                  # PDF 리포트 생성
    pipeline/                 # 전체 분석 흐름
    shared/                   # 공통 유틸

  streaming/                 # 실시간 STT/번역 기능
  evaluation/                # STT 모델별 CER 평가
  benchmark/                 # 보고서용 벤치마크 검증 자료
  app/                       # Flutter 앱 버전
```

## STT 모델 평가

평가용 데이터 목록은 아래 명령으로 만듭니다.

```powershell
python evaluation\create_evaluation_manifest.py --limit 20 --voice-limit 20 --seed 42
```

5개 STT 엔진을 돌려 CER을 계산합니다.

```powershell
python evaluation\run_stt_model_cer_benchmark.py --engines clova,azure,whisper,google,assemblyai
```

결과 검증은 아래 명령으로 진행합니다.

```powershell
python evaluation\verify_cer_summary.py
```

결과 파일은 다음 위치에 생성됩니다.

```text
evaluation/results/stt_model_cer_by_audio_file.csv
evaluation/results/stt_model_average_cer_summary.csv
evaluation/results/stt_model_transcripts_and_cer_details.csv
```

## CER 계산 방식

CER은 정답 전사문과 STT 결과 전사문을 문자 단위로 비교해서 계산합니다.

```text
CER = (Substitution + Deletion + Insertion) / Reference Characters * 100
```

즉, 임의로 값을 넣는 방식이 아니라 각 오디오 파일의 정답 문장과 모델별 전사 결과를 비교해서 파일별 CER을 만들고, 그 파일별 값으로 모델 평균을 냅니다.
