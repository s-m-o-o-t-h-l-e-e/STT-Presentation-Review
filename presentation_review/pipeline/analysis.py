from ..llm.evaluator import llm_analysis
from ..materials.extractor import extract_material_text
from ..materials.matcher import build_document_match
from ..speech_to_text.clova_speech import clova_transcribe


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


def run_analysis_from_transcript(transcript: str, material=None, name: str = "streaming-transcript") -> dict:
    clean_transcript = str(transcript or "").strip()
    result = llm_analysis(clean_transcript, name, [], [], [])
    material_info = extract_material_text(material)
    match = build_document_match(clean_transcript, material_info)
    result["audio_name"] = name
    result["document_name"] = material_info.get("name", "")
    result["document_type"] = material_info.get("type", "")
    result["document_match"] = match
    result["analysis_source"] = f"{result.get('analysis_source', 'Claude')} + streaming STT transcript"
    if match.get("available"):
        result["material_summary"] = match.get("summary", "")
    return result


__all__ = ["run_analysis", "run_analysis_from_transcript"]
