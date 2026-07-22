import cgi
import json
import re
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib import request
from urllib.error import HTTPError
from urllib.parse import urlparse

import app as analysis_app
from presentation_review.config.settings import CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_TIMEOUT_SECONDS
from presentation_review.materials.extractor import extract_material_text

ROOT = Path(__file__).parent
RECORDING_DIR = ROOT / "output" / "recordings"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}

TRANSLATION_LANGUAGES = {
    "en": "English",
    "ja": "Japanese",
    "zh": "Simplified Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "vi": "Vietnamese",
    "id": "Indonesian",
}


class UploadedFile:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def translate_text(text: str, target: str) -> str:
    if not CLAUDE_API_KEY:
        raise RuntimeError(".env에 CLAUDE_API_KEY가 없습니다.")
    language = TRANSLATION_LANGUAGES.get(target, "English")
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1600,
        "system": "You are a professional real-time speech translator.",
        "messages": [{
            "role": "user",
            "content": (
                f"Translate the following Korean speech transcript into {language}. "
                "Preserve paragraph breaks. Return only the translated text.\n\n"
                f"{text}"
            ),
        }],
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
        raise RuntimeError(f"Claude API 오류 {exc.code}: {detail}") from exc

    chunks = []
    for item in data.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(str(item.get("text", "")))
    return "\n".join(chunks).strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        self.send_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        file_path = (ROOT / path.lstrip("/")).resolve()
        if ROOT not in file_path.parents and file_path != ROOT:
            self.send_error(403)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        self.send_bytes(file_path.read_bytes(), STATIC_TYPES.get(file_path.suffix.lower(), "application/octet-stream"))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/analyze":
                self.handle_analyze()
            elif path == "/api/analyze-text":
                self.handle_analyze_text()
            elif path == "/api/translate":
                self.handle_translate()
            elif path == "/api/save-recording":
                self.handle_save_recording()
            elif path == "/api/material-preview":
                self.handle_material_preview()
            elif path == "/api/evaluate-answer":
                self.handle_evaluate_answer()
            elif path == "/api/report":
                self.handle_report()
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def material_from_form(self, form: cgi.FieldStorage) -> UploadedFile | None:
        material_field = form["material"] if "material" in form else None
        if material_field is not None and getattr(material_field, "filename", ""):
            return UploadedFile(Path(material_field.filename).name, material_field.file.read())
        return None

    def safe_filename(self, name: str, fallback: str = "recording.webm") -> str:
        cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", Path(name or fallback).name).strip(".-")
        return cleaned or fallback

    def handle_save_recording(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        field = form["audio"] if "audio" in form else None
        if field is None or not getattr(field, "filename", ""):
            self.send_json({"ok": False, "error": "저장할 녹음 파일이 없습니다."}, 400)
            return

        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        filename = self.safe_filename(field.filename)
        target = RECORDING_DIR / filename
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            index = 2
            while target.exists():
                target = RECORDING_DIR / f"{stem}-{index}{suffix}"
                index += 1

        target.write_bytes(field.file.read())

        transcript = str(form.getfirst("transcript", "") or "")
        timeline = str(form.getfirst("timeline", "") or "[]")
        meta_path = target.with_suffix(target.suffix + ".json")
        try:
            parsed_timeline = json.loads(timeline)
        except json.JSONDecodeError:
            parsed_timeline = []
        meta_path.write_text(
            json.dumps(
                {
                    "audio_file": target.name,
                    "transcript": transcript,
                    "timeline": parsed_timeline,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.send_json({"ok": True, "path": str(target.relative_to(ROOT)).replace("\\", "/")})

    def handle_analyze(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        field = form["audio"] if "audio" in form else None
        streaming_transcript = str(form.getfirst("streaming_transcript", "") or "").strip()
        streaming_timeline = self.parse_streaming_timeline(str(form.getfirst("streaming_timeline", "") or "[]"))
        material = self.material_from_form(form)

        if field is None or not getattr(field, "filename", ""):
            if streaming_transcript:
                result = analysis_app.run_analysis_from_transcript(streaming_transcript, material, "실시간 STT 전사문", streaming_timeline)
                self.send_json({"ok": True, "analysis": result})
                return
            self.send_json({"ok": False, "error": "audio 파일 또는 스트리밍 전사문이 없습니다."}, 400)
            return

        audio = UploadedFile(Path(field.filename).name, field.file.read())
        result = analysis_app.run_analysis(audio, material)
        if streaming_transcript:
            result["streaming_transcript"] = streaming_transcript
        if streaming_timeline:
            result["streaming_timeline"] = streaming_timeline
        self.send_json({"ok": True, "analysis": result})

    def parse_streaming_timeline(self, raw: str) -> list:
        try:
            parsed = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    def handle_material_preview(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        material = self.material_from_form(form)
        if material is None:
            self.send_json({"ok": False, "error": "PPT/PDF 발표자료가 없습니다."}, 400)
            return

        info = extract_material_text(material)
        sections = info.get("sections") or []
        page_count = self.material_page_count(material, info.get("type", ""), sections)
        self.send_json({
            "ok": True,
            "name": info.get("name", ""),
            "type": info.get("type", ""),
            "sections": sections,
            "page_count": page_count,
            "error": info.get("error", ""),
        })

    def material_page_count(self, material: UploadedFile, material_type: str, sections: list) -> int:
        data = material.getvalue()
        kind = str(material_type or "").upper()
        if kind == "PPTX":
            try:
                with zipfile.ZipFile(BytesIO(data)) as archive:
                    return max(1, len([name for name in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)]))
            except Exception:
                return max(1, len(sections))
        if kind == "PDF":
            try:
                try:
                    from pypdf import PdfReader
                except Exception:
                    from PyPDF2 import PdfReader
                return max(1, len(PdfReader(BytesIO(data)).pages))
            except Exception:
                return max(1, len(sections))
        return max(1, len(sections))

    def handle_analyze_text(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        transcript = str(data.get("transcript", "")).strip()
        if not transcript:
            self.send_json({"ok": False, "error": "분석할 스트리밍 전사문이 없습니다."}, 400)
            return
        result = analysis_app.run_analysis_from_transcript(transcript, None, "실시간 STT 전사문", data.get("timeline", []))
        self.send_json({"ok": True, "analysis": result})

    def handle_translate(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        text = str(data.get("text", "")).strip()
        target = str(data.get("target", "en")).strip()
        if not text:
            self.send_json({"ok": True, "translation": ""})
            return
        self.send_json({"ok": True, "translation": translate_text(text, target)})

    def handle_evaluate_answer(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        result = analysis_app.evaluate_qa_answer(
            data.get("question", {}),
            data.get("answer", ""),
            data.get("transcript", ""),
        )
        self.send_json({"ok": True, "result": result})

    def handle_report(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        analysis = json.loads(self.rfile.read(length).decode("utf-8")).get("analysis")
        if not analysis:
            self.send_json({"ok": False, "error": "analysis 데이터가 없습니다."}, 400)
            return
        pdf = analysis_app.build_report_pdf(analysis)
        self.send_bytes(pdf, "application/pdf")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8502), Handler)
    server.serve_forever()
