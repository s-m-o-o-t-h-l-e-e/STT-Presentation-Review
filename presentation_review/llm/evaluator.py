import json
import re
from typing import Any
from urllib import request
from urllib.error import HTTPError

from ..config.settings import CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_TIMEOUT_SECONDS, HAS_CLAUDE
from ..shared.utils import clamp_number, normalize_score, parse_count_text
from ..speech_analysis.metrics import (
    direct_filler_words,
    overall_wpm_from_pace,
    python_quantitative_metrics,
    section_rows_from_segments,
    transcript_wpm,
)


def extract_claude_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for content in data.get("content", []):
        if isinstance(content, dict) and content.get("type") == "text":
            chunks.append(str(content.get("text", "")))
    return "\n".join(chunks).strip()


def parse_json_object(raw: str) -> dict[str, Any]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            raise
        decoder = json.JSONDecoder()
        parsed, _ = decoder.raw_decode(raw[start:])
        if not isinstance(parsed, dict):
            raise ValueError("Claude response JSON is not an object")
        return parsed


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict[str, Any]:
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=CLAUDE_TIMEOUT_SECONDS) as res:
            data = json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Claude API {exc.code}: {detail}") from exc
    return parse_json_object(extract_claude_text(data))


def deterministic_vocabulary_suggestions(transcript: str) -> list[dict[str, Any]]:
    candidates = [
        ("이제", "다음으로, 이어서", "문장 전환 습관어를 줄이면 발표 흐름이 또렷해집니다."),
        ("그", "해당, 이", "지시어가 반복되면 대상이 흐려질 수 있습니다."),
        ("사실은", "실제로, 핵심은", "구어체 표현보다 결론형 표현이 더 적합합니다."),
        ("좀", "다소, 약간", "모호한 정도 표현을 격식 있는 표현으로 바꾸세요."),
        ("어", "문장 시작 전 0.5초 멈춤", "불필요한 발성 대신 짧은 침묵을 사용하세요."),
        ("아", "문장 시작 전 0.5초 멈춤", "생각을 정리하는 소리가 반복되면 자신감이 낮아 보일 수 있습니다."),
    ]
    return [{"original": o, "replacement": r, "reason": why} for o, r, why in candidates if o in transcript][:5]


def deterministic_problems(transcript: str, wpm: int, filler_total: int) -> list[dict[str, Any]]:
    problems = []
    if wpm < 100:
        problems.append({"category": "전달력", "level": "주의", "title": "발화 속도가 느리거나 공백이 길게 이어집니다.", "fix": "문장 사이 불필요한 공백과 반복 표현을 줄이세요."})
    elif wpm > 155:
        problems.append({"category": "전달력", "level": "주의", "title": "발화 속도가 빠른 구간이 있어 핵심 메시지가 지나갈 수 있습니다.", "fix": "중요 수치와 결론 뒤에는 1초 정도 멈추세요."})
    if filler_total >= 10:
        problems.append({"category": "발표 습관", "level": "심각", "title": "추임새가 반복되어 발표 전문성이 약해 보입니다.", "fix": "어/아/이제/그가 나오는 위치를 표시하고 짧은 침묵으로 대체하세요."})
    if len(transcript) < 500:
        problems.append({"category": "내용", "level": "주의", "title": "전사된 발표 내용이 짧아 심사 근거가 충분히 드러나지 않습니다.", "fix": "문제, 해결책, 시장성, 수익모델, 팀 역량을 각각 두 문장 이상 보강하세요."})
    if not problems:
        problems.append({"category": "구성", "level": "경미", "title": "발표 구조를 더 명확히 나누면 심사위원이 따라가기 쉽습니다.", "fix": "도입, 문제, 해결책, 근거, 요청사항 순서로 전환 문장을 넣으세요."})
    return problems[:4]


def deterministic_questions(transcript: str) -> list[dict[str, Any]]:
    return [
        {"category": "문제정의", "question": "현재 제시한 문제가 실제 고객에게 얼마나 자주 발생하나요?", "level": "보통"},
        {"category": "고객", "question": "초기 핵심 고객군은 누구이며 왜 지금 구매해야 하나요?", "level": "보통"},
        {"category": "시장", "question": "시장 규모 산정 근거와 출처는 무엇인가요?", "level": "어려움"},
        {"category": "경쟁", "question": "기존 대안이나 경쟁사 대비 명확한 차별점은 무엇인가요?", "level": "어려움"},
        {"category": "수익성", "question": "가격 정책과 원가 구조를 고려했을 때 수익성은 어떻게 확보하나요?", "level": "보통"},
        {"category": "실행", "question": "지원금 또는 투자금이 들어오면 가장 먼저 실행할 항목은 무엇인가요?", "level": "쉬움"},
        {"category": "검증", "question": "현재까지 고객 검증이나 파일럿 결과가 있나요?", "level": "보통"},
        {"category": "리스크", "question": "가장 큰 사업 리스크와 대응 계획은 무엇인가요?", "level": "어려움"},
        {"category": "팀", "question": "팀이 이 문제를 가장 잘 해결할 수 있는 근거는 무엇인가요?", "level": "보통"},
        {"category": "성과", "question": "6개월 안에 달성할 핵심 지표는 무엇인가요?", "level": "보통"},
    ]


def fallback_analysis(transcript: str, audio_name: str, message: str = "") -> dict[str, Any]:
    wpm = transcript_wpm(transcript)
    fillers = direct_filler_words(transcript)
    return {
        "audio_name": audio_name,
        "transcript": transcript,
        "score": 0,
        "grade": "-",
        "status": "모델 평가 필요",
        "wpm": wpm,
        "filler_total": sum(item["count"] for item in fillers),
        "vocab_issues": 0,
        "voice_scores": {"발표 흐름": 0, "내용 전달력": 0, "Q&A 대응": 0, "시간 관리": 0},
        "filler_counts": {item["word"]: item["count"] for item in fillers},
        "filler_words": fillers,
        "vocab_suggestions": [],
        "pace_series": [{"time": f"{i}:00", "wpm": wpm} for i in range(7)],
        "sentence_segments": [],
        "speaker_stats": [],
        "slide_rows": [],
        "problems": [],
        "questions": [],
        "summary": message or "Claude 모델 평가가 완료되지 않았습니다.",
        "improvement_priorities": [],
        "analysis_source": "모델 평가 미완료",
        "llm_used": False,
    }


def enrich_fallback_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    wpm = clamp_number(analysis.get("wpm"), 120, 0, 500)
    filler_total = clamp_number(analysis.get("filler_total"), 0, 0, 999)
    score = 82 - min(24, abs(wpm - 135) // 3) - min(18, filler_total // 2)
    score = clamp_number(score, 60, 35, 88)
    analysis["score"] = score
    analysis["grade"] = "B+" if score >= 76 else "B" if score >= 65 else "C"
    analysis["status"] = "보완 필요" if score < 75 else "통과 예상"
    analysis["vocab_suggestions"] = deterministic_vocabulary_suggestions(analysis.get("transcript", ""))
    analysis["vocab_issues"] = len(analysis["vocab_suggestions"])
    analysis["voice_scores"] = {
        "발표 흐름": clamp_number(score + (4 if 110 <= wpm <= 150 else -6), score, 0, 100),
        "내용 전달력": clamp_number(score - min(10, filler_total // 3), score, 0, 100),
        "Q&A 대응": clamp_number(score - 8, score, 0, 100),
        "시간 관리": clamp_number(88 - abs(wpm - 135) // 2, score, 0, 100),
    }
    analysis["problems"] = deterministic_problems(analysis.get("transcript", ""), wpm, filler_total)
    analysis["questions"] = deterministic_questions(analysis.get("transcript", ""))
    analysis["improvement_priorities"] = [
        {"title": "추임새 축소", "impact": "높음", "detail": "반복되는 추임새 위치를 표시하고 문장 시작 전 짧은 침묵으로 대체하세요."},
        {"title": "속도 안정화", "impact": "중간", "detail": "문장 구간별 WPM이 과도하게 높거나 낮은 구간을 중심으로 녹음 연습하세요."},
        {"title": "핵심 근거 보강", "impact": "높음", "detail": "시장 규모, 고객 문제, 차별점에 정량 근거를 추가하세요."},
    ]
    if not analysis.get("summary"):
        analysis["summary"] = "CLOVA 전사와 timestamp 기준으로 기본 평가를 생성했습니다."
    return analysis


def merge_fillers(model_items: list[Any], transcript: str) -> list[dict[str, Any]]:
    return direct_filler_words(transcript)


def sync_speaker_stats(analysis: dict[str, Any]) -> dict[str, Any]:
    speakers = analysis.get("speaker_stats")
    if not isinstance(speakers, list) or not speakers:
        return analysis
    filler_total = sum(clamp_number(item.get("count"), 0, 0, 999) for item in analysis.get("filler_words", []) if isinstance(item, dict))
    analysis["filler_total"] = filler_total
    valid_rows = [row for row in speakers if isinstance(row, dict)]
    if len(valid_rows) == 1:
        valid_rows[0]["wpm"] = clamp_number(analysis.get("wpm"), valid_rows[0].get("wpm", 0), 0, 500)
        valid_rows[0]["fillers"] = filler_total
    return analysis


def sync_slide_filler_totals(analysis: dict[str, Any]) -> dict[str, Any]:
    rows = analysis.get("slide_rows")
    if not isinstance(rows, list) or not rows:
        return analysis
    filler_total = clamp_number(analysis.get("filler_total"), 0, 0, 999)
    valid_rows = [row for row in rows if isinstance(row, dict)]
    if not valid_rows:
        return analysis
    if filler_total <= 0:
        for row in valid_rows:
            row["fillers"] = "0회"
        return analysis
    weights = [parse_count_text(row.get("fillers")) or parse_count_text(row.get("duration")) or 1 for row in valid_rows]
    weight_sum = sum(weights) or len(valid_rows)
    assigned = []
    remainders = []
    running = 0
    for weight in weights:
        raw = filler_total * weight / weight_sum
        value = int(raw)
        assigned.append(value)
        remainders.append(raw - value)
        running += value
    for idx in sorted(range(len(assigned)), key=lambda i: remainders[i], reverse=True)[:max(0, filler_total - running)]:
        assigned[idx] += 1
    for row, value in zip(valid_rows, assigned):
        row["fillers"] = f"{value}회"
    return analysis


def sync_consistent_counts(analysis: dict[str, Any]) -> dict[str, Any]:
    return sync_slide_filler_totals(sync_speaker_stats(analysis))


def text_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        return ", ".join(text_value(item) for item in value if text_value(item))
    if isinstance(value, dict):
        for key in ("title", "question", "detail", "fix", "summary", "text", "value", "name", "category", "reason"):
            if value.get(key):
                return text_value(value.get(key), default)
    return default


def meaningful_text(value: Any, default: str = "") -> str:
    text = text_value(value, default).strip()
    if not text or re.fullmatch(r"\d+\.?", text):
        return ""
    return text


def clean_problem_items(items: Any) -> list[dict[str, Any]]:
    cleaned = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            row = {"category": "문제", "level": "확인", "title": meaningful_text(item), "fix": ""}
        else:
            row = {
                "category": text_value(item.get("category") if isinstance(item, dict) else "", "문제"),
                "level": text_value(item.get("level") if isinstance(item, dict) else "", "확인"),
                "title": meaningful_text((item.get("title") or item.get("problem") or item.get("issue")) if isinstance(item, dict) else ""),
                "fix": meaningful_text((item.get("fix") or item.get("solution") or item.get("detail")) if isinstance(item, dict) else ""),
            }
        if row["title"] or row["fix"]:
            cleaned.append(row)
    return cleaned


def clean_question_items(items: Any) -> list[dict[str, Any]]:
    cleaned = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            row = {"category": "질문", "question": meaningful_text(item), "level": "-"}
        else:
            row = {
                "category": text_value((item.get("category") or item.get("type")) if isinstance(item, dict) else "", "질문"),
                "question": meaningful_text((item.get("question") or item.get("title") or item.get("text")) if isinstance(item, dict) else ""),
                "level": text_value((item.get("level") or item.get("difficulty")) if isinstance(item, dict) else "", "-"),
            }
        if row["question"]:
            cleaned.append(row)
    return cleaned


def clean_priority_items(items: Any) -> list[dict[str, Any]]:
    cleaned = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            row = {"title": meaningful_text(item), "impact": "", "detail": ""}
        else:
            row = {
                "title": meaningful_text((item.get("title") or item.get("priority") or item.get("name")) if isinstance(item, dict) else ""),
                "impact": text_value((item.get("impact") or item.get("level")) if isinstance(item, dict) else ""),
                "detail": meaningful_text((item.get("detail") or item.get("fix") or item.get("reason")) if isinstance(item, dict) else ""),
            }
        if row["title"] or row["detail"]:
            cleaned.append(row)
    return cleaned


def clean_vocab_suggestions(items: Any) -> list[dict[str, Any]]:
    cleaned = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            row = {"original": item, "replacement": "", "reason": ""}
        elif isinstance(item, dict):
            row = {
                "original": text_value(item.get("original") or item.get("before") or item.get("word") or item.get("expression")),
                "replacement": text_value(item.get("replacement") or item.get("after") or item.get("suggestion")),
                "reason": text_value(item.get("reason") or item.get("detail")),
            }
        else:
            row = {"original": "", "replacement": "", "reason": ""}
        if row["original"] or row["replacement"] or row["reason"]:
            cleaned.append(row)
    return cleaned


def vocab_issue_count(value: Any, suggestions: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return clamp_number(value, len(suggestions) if isinstance(suggestions, list) else 0, 0, 999)


def fallback_voice_scores(score: int, wpm: int, filler_total: int) -> dict[str, int]:
    return {
        "발표 흐름": clamp_number(score + (3 if 110 <= wpm <= 150 else -8), score, 0, 100),
        "내용 전달력": clamp_number(score - min(14, filler_total // 4), score, 0, 100),
        "Q&A 대응": clamp_number(score - 8, score, 0, 100),
        "시간 관리": clamp_number(90 - abs(wpm - 135) // 2, score, 0, 100),
    }


def normalize_analysis(judged: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in judged.items():
        if key in {"transcript", "audio_name", "filler_words", "filler_total", "filler_counts"}:
            continue
        if value not in [None, ""]:
            result[key] = value
    result["score"] = clamp_number(result.get("score"), 0, 0, 100)
    result["wpm"] = clamp_number(result.get("wpm"), base["wpm"], 0, 500)
    voice = result.get("voice_scores") if isinstance(result.get("voice_scores"), dict) else {}
    result["voice_scores"] = {key: clamp_number(voice.get(key), 0, 0, 100) for key in ["발표 흐름", "내용 전달력", "Q&A 대응", "시간 관리"]}
    for key in ["pace_series", "sentence_segments", "speaker_stats", "filler_words", "vocab_suggestions", "slide_rows", "problems", "questions", "improvement_priorities"]:
        if not isinstance(result.get(key), list):
            result[key] = []
    result["vocab_suggestions"] = clean_vocab_suggestions(result.get("vocab_suggestions"))
    result["vocab_issues"] = vocab_issue_count(result.get("vocab_issues"), result.get("vocab_suggestions", []))
    result["problems"] = clean_problem_items(result.get("problems"))
    result["questions"] = clean_question_items(result.get("questions"))
    result["improvement_priorities"] = clean_priority_items(result.get("improvement_priorities"))
    result["filler_words"] = merge_fillers(result["filler_words"], result.get("transcript", ""))
    result["filler_total"] = sum(clamp_number(item.get("count"), 0, 0, 999) for item in result["filler_words"])
    result["filler_counts"] = {str(item["word"]): item["count"] for item in result["filler_words"] if item.get("word")}
    if sum(result["voice_scores"].values()) == 0 and result["score"] > 0:
        result["voice_scores"] = fallback_voice_scores(result["score"], result["wpm"], result["filler_total"])
    result["analysis_source"] = "CLOVA Speech + Claude"
    result["llm_used"] = True
    return sync_consistent_counts(result)


def llm_analysis(transcript: str, audio_name: str, measured_pace: list[dict[str, Any]] | None = None, sentence_segments: list[dict[str, Any]] | None = None, speaker_stats: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    base = fallback_analysis(transcript, audio_name)
    sentence_segments = sentence_segments or []
    speaker_stats = speaker_stats or []
    quantitative_metrics = python_quantitative_metrics(transcript, measured_pace, sentence_segments, speaker_stats)
    base["quantitative_metrics"] = quantitative_metrics
    if sentence_segments:
        base["sentence_segments"] = sentence_segments
        base["slide_rows"] = section_rows_from_segments(sentence_segments, measured_pace)
    if speaker_stats:
        base["speaker_stats"] = speaker_stats
    if measured_pace:
        base["pace_series"] = measured_pace
        base["wpm"] = overall_wpm_from_pace(measured_pace, base["wpm"])
    if not HAS_CLAUDE:
        no_key = fallback_analysis(transcript, audio_name, "Claude API key is missing.")
        no_key.update({
            "pace_series": base.get("pace_series", []),
            "wpm": base.get("wpm"),
            "sentence_segments": sentence_segments,
            "speaker_stats": speaker_stats,
            "slide_rows": section_rows_from_segments(sentence_segments, measured_pace),
            "quantitative_metrics": quantitative_metrics,
        })
        return sync_consistent_counts(enrich_fallback_analysis(no_key))
    if not transcript.strip():
        return fallback_analysis(transcript, audio_name, "CLOVA Speech transcript is empty.")

    system_prompt = "You are a Korean IR presentation reviewer. Return JSON only."
    user_prompt = (
        "Evaluate this Korean presentation. Use Python metrics as the source of truth for WPM, filler counts, pauses, and timestamps.\n"
        "Return JSON with keys: score, grade, status, wpm, vocab_issues, voice_scores, pace_series, filler_words, vocab_suggestions, slide_rows, problems, questions, improvement_priorities, summary.\n"
        "Generate exactly 10 questions.\n\n"
        f"[Python metrics]\n{json.dumps(quantitative_metrics, ensure_ascii=False)}\n\n"
        f"[Sentence timeline]\n{json.dumps(sentence_segments[:160], ensure_ascii=False)}\n\n"
        f"[Speaker stats]\n{json.dumps(speaker_stats, ensure_ascii=False)}\n\n"
        f"[STT transcript]\n{transcript[:7000]}"
    )
    try:
        result = normalize_analysis(call_claude(system_prompt, user_prompt, max_tokens=5000), base)
        result["pace_series"] = base.get("pace_series", result.get("pace_series", []))
        result["wpm"] = base.get("wpm", result.get("wpm", 0))
        result["sentence_segments"] = sentence_segments
        result["speaker_stats"] = speaker_stats
        result["slide_rows"] = section_rows_from_segments(sentence_segments, measured_pace) or result.get("slide_rows", [])
        result["quantitative_metrics"] = quantitative_metrics
        return sync_consistent_counts(result)
    except Exception as exc:
        failed = fallback_analysis(transcript, audio_name, f"Claude model evaluation failed: {exc}")
        failed.update({
            "pace_series": base.get("pace_series", []),
            "wpm": base.get("wpm"),
            "sentence_segments": sentence_segments,
            "speaker_stats": speaker_stats,
            "slide_rows": section_rows_from_segments(sentence_segments, measured_pace),
            "quantitative_metrics": quantitative_metrics,
        })
        return sync_consistent_counts(enrich_fallback_analysis(failed))


def evaluate_qa_answer(question: dict[str, Any], answer: str, transcript: str) -> dict[str, Any]:
    if not HAS_CLAUDE:
        return {"score": 0, "logic": 0, "specificity": 0, "confidence": 0, "time_control": 0, "strengths": [], "improvements": ["Claude API 키가 없습니다."], "model_answer": "", "tags": []}
    system_prompt = "너는 한국어 IR 발표 Q&A 심사위원이다. 설명 문장 없이 JSON 객체만 반환한다."
    user_prompt = (
        "예상 질문에 대한 발표자의 답변을 평가하라. JSON 형식: "
        "{score:number, logic:number, specificity:number, confidence:number, time_control:number, strengths:[string], improvements:[string], model_answer:string, tags:[string]}\n\n"
        f"[발표 전사]\n{transcript[:3000]}\n\n[질문]\n{question.get('question', '')}\n\n[답변]\n{answer[:3000]}"
    )
    try:
        judged = call_claude(system_prompt, user_prompt, max_tokens=2500)
    except Exception as exc:
        return {"score": 0, "logic": 0, "specificity": 0, "confidence": 0, "time_control": 0, "strengths": [], "improvements": [f"답변 평가 오류: {exc}"], "model_answer": "", "tags": []}
    return {
        "score": normalize_score(judged.get("score"), 0),
        "logic": normalize_score(judged.get("logic"), 0),
        "specificity": normalize_score(judged.get("specificity"), 0),
        "confidence": normalize_score(judged.get("confidence"), 0),
        "time_control": normalize_score(judged.get("time_control"), 0),
        "strengths": judged.get("strengths") if isinstance(judged.get("strengths"), list) else [],
        "improvements": judged.get("improvements") if isinstance(judged.get("improvements"), list) else [],
        "model_answer": str(judged.get("model_answer", "")),
        "tags": judged.get("tags") if isinstance(judged.get("tags"), list) else [],
    }
