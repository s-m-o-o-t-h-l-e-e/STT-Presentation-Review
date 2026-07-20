# STT Presentation Review

발표 음성을 기반으로 발표 품질을 분석하고, 발표자료와 실제 발화 내용의 일치율까지 점검하는 AI 발표 사전심사 플랫폼입니다.

Naver CLOVA Speech로 발표 음성을 전사하고, Python 기반 정량 분석과 Claude 기반 정성 평가를 결합해 발표 흐름, 발화 속도, 추임새, 예상 질문, 개선 포인트, 자료 반영률을 한 번에 확인할 수 있습니다.

## 서비스 개요

초기 창업팀, IR 발표자, 지원사업 발표 준비자를 대상으로 발표 전 사전 점검을 돕는 웹 기반 분석 도구입니다.

음성 파일을 업로드하면 STT 전사와 timestamp 분석을 수행하고, 발표자가 실제로 말한 내용이 발표자료와 얼마나 일치하는지 비교합니다. 분석 결과는 화면에서 확인하거나 PDF 리포트로 다운로드할 수 있습니다.

## 핵심 기능

| 기능 | 설명 |
| --- | --- |
| 발표 음성 전사 | Naver CLOVA Speech를 이용해 한국어 발표 음성을 전사합니다. |
| 문장별 타임라인 | 문장 단위 발화 구간, 공백 시간, 화자 정보를 정리합니다. |
| 발화 속도 분석 | 실제 음성 길이와 단어 수를 기준으로 WPM을 계산합니다. |
| 추임새 분석 | 전사문에서 반복적으로 등장하는 추임새를 집계합니다. |
| 화자별 분석 | CLOVA Speech의 화자 정보를 기반으로 발화 비중을 분석합니다. |
| 발표자료 매칭 | PPT/PDF 자료와 발표 전사문을 비교해 자료 반영률을 계산합니다. |
| AI 발표 평가 | Claude 모델을 이용해 문제점, 보완사항, 예상 질문을 생성합니다. |
| PDF 리포트 | 점수, 그래프, 피드백, 자료 매칭 결과를 포함한 리포트를 생성합니다. |
| 실시간 STT | 음성 파일이 없는 경우 브라우저 기반 실시간 STT로 분석을 보조합니다. |

## 분석 프로세스

```text
발표 음성 업로드
→ CLOVA Speech 전사 및 timestamp 추출
→ Python 정량 지표 계산
→ 발표자료 PPT/PDF 텍스트 추출
→ 전사문과 발표자료 일치율 비교
→ Claude 기반 발표 품질 평가
→ 화면 시각화 및 PDF 리포트 생성
```

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | HTML, CSS, JavaScript |
| Backend | Python HTTP Server |
| STT | Naver CLOVA Speech |
| LLM | Claude API |
| Document Parsing | pypdf, PPTX XML parsing |
| Visualization | matplotlib |
| PDF Report | ReportLab |
| Environment | python-dotenv |

## 프로젝트 구조

```text
stt-presentation-review/
├─ server.py                         # 로컬 웹 서버 및 API 라우팅
├─ app.py                            # 기존 코드 호환용 진입 파일
├─ index.html                        # 메인 화면
├─ app.js                            # 화면 동작 및 API 호출
├─ styles.css                        # UI 스타일
├─ requirements.txt                  # Python 의존성
├─ .env.example                      # 환경변수 예시
├─ .gitignore                        # Git 제외 파일
└─ presentation_review/
   ├─ config/                        # 환경변수와 서비스 설정
   ├─ speech_to_text/                # CLOVA STT 호출 및 timestamp 처리
   ├─ speech_analysis/               # 발화 속도, 추임새, 화자 지표 계산
   ├─ materials/                     # PPT/PDF 텍스트 추출 및 자료 매칭
   ├─ llm/                           # Claude 기반 발표 평가
   ├─ reports/                       # PDF 리포트 생성
   ├─ pipeline/                      # 전체 분석 파이프라인
   └─ shared/                        # 공통 유틸 함수
```

## 실행 방법

### 1. 패키지 설치

```powershell
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`을 참고해 프로젝트 루트에 `.env` 파일을 생성합니다.

```env
CLOVA_SPEECH_SECRET_KEY=
CLOVA_SPEECH_INVOKE_URL=
CLAUDE_API_KEY=
CLAUDE_MODEL=choose_CLAUDE_key
CLAUDE_TIMEOUT_SECONDS=180
```

### 3. 서버 실행

```powershell
python server.py
```

### 4. 접속 주소

```text
http://127.0.0.1:8502
```

## 향후 개선 방향

- STT 모델별 전사 결과 비교
- 화자 분리 정확도 개선
- 실시간 STT 결과 기반 즉시 피드백
- 발표자료 기반 예상 질문 고도화
- 긴 음성 파일 처리 속도 개선
- 리포트 디자인 고도화
