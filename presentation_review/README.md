# presentation_review

발표 평가 기능을 역할별로 나눈 Python 패키지입니다.

## 폴더 구조

| 폴더 | 역할 |
| --- | --- |
| `config/` | `.env` 값을 읽고 API 설정 관리 |
| `speech_to_text/` | CLOVA Speech 호출, 음성 길이 확인, timestamp 정리 |
| `speech_analysis/` | WPM, 추임새, 공백, 화자별 지표 계산 |
| `materials/` | PPT/PDF 발표자료 텍스트 추출과 전사문 매칭 |
| `llm/` | Claude 모델을 이용한 발표 평가 |
| `reports/` | PDF 리포트 생성 |
| `pipeline/` | 전체 분석 과정을 하나로 연결 |
| `shared/` | 공통 유틸 함수 |

## 처리 흐름

```text
speech_to_text
→ speech_analysis
→ materials
→ llm
→ reports
```

기능별 파일을 분리해서 `server.py`가 너무 길어지지 않도록 구성했습니다.
