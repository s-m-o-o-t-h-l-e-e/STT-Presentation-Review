from ..llm.evaluator import llm_analysis
from ..materials.extractor import extract_material_text
from ..materials.matcher import build_document_match
from ..speech_analysis.metrics import pace_from_timings, speaker_stats_from_segments, timing_units_from_segments
from ..speech_to_text.clova_speech import clova_transcribe


def segments_from_streaming_timeline(timeline) -> list[dict]:
    segments = []
    for idx, item in enumerate(timeline if isinstance(timeline, list) else [], 1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "") or "").strip()
        if not text:
            continue
        try:
            start = float(item.get("start", 0) or 0)
            end = float(item.get("end", start) or start)
        except (TypeError, ValueError):
            start, end = 0.0, 0.0
        if end <= start:
            end = start + max(1.0, len(text.split()) / 1.7)
        gap = 0.0
        if segments:
            gap = max(0.0, start - float(segments[-1].get("end", 0) or 0))
        segments.append({
            "time": item.get("time") or f"{int(start // 60):02d}:{int(start % 60):02d}-{int(end // 60):02d}:{int(end % 60):02d}",
            "start": round(start, 2),
            "end": round(end, 2),
            "speaker": item.get("speaker") or "화자 1",
            "section": item.get("page") or item.get("section") or 1,
            "gap_before": round(gap, 2),
            "text": text,
        })
    return segments


def run_analysis(audio, material=None) -> dict:
    transcript, measured_pace, sentence_segments, speaker_stats = clova_transcribe(audio)
    result = llm_analysis(transcript, audio.name if audio else "uploaded-audio", measured_pace, sentence_segments, speaker_stats)
    material_info = extract_material_text(material)
    match = build_document_match(transcript, material_info)
    result["document_name"] = material_info.get("name", "")
    result["document_type"] = material_info.get("type", "")
    result["document_match"] = match
    if match.get("available"):
        result["material_summary"] = match.get("summary", "")
    return result


def run_analysis_from_transcript(transcript: str, material=None, name: str = "streaming-transcript", timeline=None) -> dict:
    clean_transcript = str(transcript or "").strip()
    sentence_segments = segments_from_streaming_timeline(timeline)
    measured_pace = pace_from_timings(timing_units_from_segments(sentence_segments), total_end=max((item["end"] for item in sentence_segments), default=0))
    speaker_stats = speaker_stats_from_segments(sentence_segments) if sentence_segments else []
    result = llm_analysis(clean_transcript, name, measured_pace, sentence_segments, speaker_stats)
    material_info = extract_material_text(material)
    match = build_document_match(clean_transcript, material_info)
    result["audio_name"] = name
    result["document_name"] = material_info.get("name", "")
    result["document_type"] = material_info.get("type", "")
    result["document_match"] = match
    result["analysis_source"] = f"{result.get('analysis_source', 'Claude')} + streaming STT transcript/timeline"
    if match.get("available"):
        result["material_summary"] = match.get("summary", "")
    return result


__all__ = ["run_analysis", "run_analysis_from_transcript", "segments_from_streaming_timeline"]
