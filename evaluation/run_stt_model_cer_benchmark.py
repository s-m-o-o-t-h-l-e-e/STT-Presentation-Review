import argparse
import base64
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from dotenv import dotenv_values, load_dotenv


ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "evaluation"
DEFAULT_MANIFEST = EVALUATION_DIR / "speech_audio_reference_manifest.csv"
RESULT_DIR = EVALUATION_DIR / "results"
LONG_CSV = RESULT_DIR / "stt_model_transcripts_and_cer_details.csv"
MATRIX_CSV = RESULT_DIR / "stt_model_cer_by_audio_file.csv"
SUMMARY_CSV = RESULT_DIR / "stt_model_average_cer_summary.csv"

ENGINES = ["clova", "azure", "whisper", "google", "assemblyai"]
CER_COLUMNS = {engine: f"{engine}_cer" for engine in ENGINES}


ENV_PATH = ROOT / ".env.private"
if not ENV_PATH.exists():
    ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH, override=True)
RAW_DOTENV = {key.lstrip("\ufeff"): value for key, value in dotenv_values(ENV_PATH).items() if key}


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name) or RAW_DOTENV.get(name)
        if value:
            return value.strip()
    return default


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-z가-힣]", "", text)
    return text


def levenshtein_counts(reference: str, hypothesis: str) -> tuple[int, int, int]:
    ref = list(reference)
    hyp = list(hypothesis)
    dp: list[list[tuple[int, int, int, int]]] = [[(0, 0, 0, 0) for _ in range(len(hyp) + 1)] for _ in range(len(ref) + 1)]
    for i in range(1, len(ref) + 1):
        cost, s, d, ins = dp[i - 1][0]
        dp[i][0] = (cost + 1, s, d + 1, ins)
    for j in range(1, len(hyp) + 1):
        cost, s, d, ins = dp[0][j - 1]
        dp[0][j] = (cost + 1, s, d, ins + 1)
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                same = dp[i - 1][j - 1]
            else:
                cost, s, d, ins = dp[i - 1][j - 1]
                same = (cost + 1, s + 1, d, ins)
            cost, s, d, ins = dp[i - 1][j]
            delete = (cost + 1, s, d + 1, ins)
            cost, s, d, ins = dp[i][j - 1]
            insert = (cost + 1, s, d, ins + 1)
            dp[i][j] = min(same, delete, insert, key=lambda item: (item[0], item[1] + item[2] + item[3]))
    _, substitutions, deletions, insertions = dp[-1][-1]
    return substitutions, deletions, insertions


def cer(reference: str, hypothesis: str) -> dict[str, Any]:
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)
    substitutions, deletions, insertions = levenshtein_counts(ref_norm, hyp_norm)
    total = len(ref_norm)
    value = round((substitutions + deletions + insertions) / total * 100, 2) if total else 0.0
    return {
        "substitution": substitutions,
        "deletion": deletions,
        "insertion": insertions,
        "reference_chars": total,
        "cer": value,
    }


def read_reference(row: dict[str, str]) -> str:
    if row.get("reference_text"):
        return extract_reference_text(row["reference_text"])
    path = (row.get("reference_path") or "").strip()
    if not path:
        raise ValueError(f"{row.get('audio_id')}: reference_text 또는 reference_path가 필요합니다.")
    ref_path = Path(path)
    if not ref_path.is_absolute():
        ref_path = ROOT / ref_path
    return extract_reference_text(read_text_any_encoding(ref_path))


def read_text_any_encoding(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def flatten_json_text(value: Any) -> list[str]:
    text_keys = {
        "text", "transcript", "transcription", "sentence", "utterance", "script",
        "original", "normalized", "발화", "원문", "전사", "문장",
    }
    if isinstance(value, dict):
        texts: list[str] = []
        for key, child in value.items():
            if key in text_keys and isinstance(child, str):
                texts.append(child)
            else:
                texts.extend(flatten_json_text(child))
        return texts
    if isinstance(value, list):
        texts: list[str] = []
        for child in value:
            texts.extend(flatten_json_text(child))
        return texts
    return []


def extract_reference_text(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    extracted = [item.strip() for item in flatten_json_text(parsed) if item and item.strip()]
    return " ".join(extracted) if extracted else stripped


def ensure_audio(row: dict[str, str]) -> Path:
    audio_path = Path((row.get("audio_path") or "").strip())
    if not audio_path:
        raise ValueError(f"{row.get('audio_id')}: audio_path가 필요합니다.")
    if not audio_path.is_absolute():
        audio_path = ROOT / audio_path
    if audio_path.exists():
        return audio_path
    url = (row.get("audio_url") or "").strip()
    if not url:
        raise FileNotFoundError(f"audio file not found: {audio_path}")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"download: {url} -> {audio_path}")
    request.urlretrieve(url, audio_path)
    return audio_path


def http_json(url: str, payload: dict[str, Any] | bytes | None = None, headers: dict[str, str] | None = None, method: str = "POST", timeout: int = 180) -> Any:
    data = payload
    if isinstance(payload, dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", **(headers or {})}
    req = request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def multipart_upload(url: str, fields: dict[str, str], file_field: str, file_path: Path, headers: dict[str, str]) -> Any:
    boundary = "----STTCERBenchmarkBoundary"
    body: list[bytes] = []
    for name, value in fields.items():
        body.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    body.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req_headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", **headers}
    return http_json(url, b"".join(body), req_headers, timeout=240)


def transcribe_clova(audio_path: Path) -> str:
    secret = env_value("CLOVA_SPEECH_SECRET_KEY", "CLOVA_SECRET_KEY", "CLOVA_SECRET")
    invoke_url = env_value("CLOVA_SPEECH_INVOKE_URL", "CLOVA_INVOKE_URL", "CLOVA_INVOKE_KEY").rstrip("/")
    if not secret or not invoke_url:
        raise RuntimeError("missing CLOVA_SPEECH_SECRET_KEY or CLOVA_SPEECH_INVOKE_URL")
    url = invoke_url if invoke_url.endswith("/recognizer/upload") else f"{invoke_url}/recognizer/upload"
    params = {
        "language": "ko-KR",
        "completion": "sync",
        "wordAlignment": True,
        "fullText": True,
        "diarization": {"enable": True, "speakerCountMin": 1, "speakerCountMax": 4},
    }
    data = multipart_upload(
        url,
        {"params": json.dumps(params, ensure_ascii=False)},
        "media",
        audio_path,
        {"Accept": "application/json;UTF-8", "X-CLOVASPEECH-API-KEY": secret},
    )
    return data.get("text") or data.get("fullText") or " ".join(seg.get("text", "") for seg in data.get("segments", []))


def transcribe_whisper(audio_path: Path) -> str:
    key = env_value("OPENAI_API_KEY")
    model = env_value("OPENAI_WHISPER_MODEL", default="whisper-1")
    if not key:
        raise RuntimeError("missing OPENAI_API_KEY")
    boundary = "----WhisperBoundary"
    body = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="model"\r\n\r\n',
        model.encode(),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="language"\r\n\r\nko\r\n',
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
        audio_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    data = http_json(
        "https://api.openai.com/v1/audio/transcriptions",
        b"".join(body),
        {"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=240,
    )
    return data.get("text", "")


def transcribe_azure(audio_path: Path) -> str:
    key = env_value("AZURE_SPEECH_KEY")
    region = env_value("AZURE_SPEECH_REGION")
    if not key or not region:
        raise RuntimeError("missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")
    url = f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=ko-KR"
    data = http_json(
        url,
        audio_path.read_bytes(),
        {
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        },
        timeout=180,
    )
    return data.get("DisplayText") or data.get("Text") or ""


def transcribe_google(audio_path: Path) -> str:
    credentials_path = env_value("GOOGLE_APPLICATION_CREDENTIALS")
    project_id = env_value("GOOGLE_CLOUD_PROJECT")
    if credentials_path and project_id:
        return transcribe_google_v2(audio_path, Path(credentials_path), project_id)
    api_key = env_value("GOOGLE_SPEECH_API_KEY")
    if not api_key:
        raise RuntimeError("missing GOOGLE_APPLICATION_CREDENTIALS/GOOGLE_CLOUD_PROJECT or GOOGLE_SPEECH_API_KEY")
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={parse.quote(api_key)}"
    payload = {
        "config": {
            "languageCode": "ko-KR",
            "enableAutomaticPunctuation": True,
        },
        "audio": {"content": base64.b64encode(audio_path.read_bytes()).decode("ascii")},
    }
    data = http_json(url, payload, timeout=180)
    return " ".join(alt.get("transcript", "") for result in data.get("results", []) for alt in result.get("alternatives", [])[:1])


def google_access_token(credentials_path: Path) -> str:
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("missing google-auth package. Run: pip install google-auth") from exc
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    credentials = service_account.Credentials.from_service_account_file(str(credentials_path), scopes=scopes)
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


def transcribe_google_v2(audio_path: Path, credentials_path: Path, project_id: str) -> str:
    if not credentials_path.exists():
        raise FileNotFoundError(f"Google service account JSON not found: {credentials_path}")
    location = env_value("GOOGLE_SPEECH_LOCATION", default="global")
    recognizer = env_value("GOOGLE_SPEECH_RECOGNIZER", default="_")
    token = google_access_token(credentials_path)
    url = (
        "https://speech.googleapis.com/v2/"
        f"projects/{parse.quote(project_id)}/locations/{parse.quote(location)}/"
        f"recognizers/{parse.quote(recognizer)}:recognize"
    )
    payload = {
        "config": {
            "autoDecodingConfig": {},
            "languageCodes": ["ko-KR"],
            "model": "latest_long",
            "features": {"enableAutomaticPunctuation": True},
        },
        "content": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
    }
    data = http_json(url, payload, {"Authorization": f"Bearer {token}"}, timeout=180)
    return " ".join(
        alt.get("transcript", "")
        for result in data.get("results", [])
        for alt in result.get("alternatives", [])[:1]
    )


def transcribe_assemblyai(audio_path: Path) -> str:
    key = env_value("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError("missing ASSEMBLYAI_API_KEY")
    upload_req = request.Request(
        "https://api.assemblyai.com/v2/upload",
        data=audio_path.read_bytes(),
        headers={"authorization": key},
        method="POST",
    )
    with request.urlopen(upload_req, timeout=240) as res:
        upload_url = json.loads(res.read().decode("utf-8"))["upload_url"]
    job = http_json(
        "https://api.assemblyai.com/v2/transcript",
        {"audio_url": upload_url, "language_code": "ko"},
        {"authorization": key},
        timeout=180,
    )
    transcript_id = job["id"]
    poll_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    for _ in range(90):
        result = http_json(poll_url, None, {"authorization": key}, method="GET", timeout=60)
        if result.get("status") == "completed":
            return result.get("text", "")
        if result.get("status") == "error":
            raise RuntimeError(result.get("error", "AssemblyAI transcription failed"))
        time.sleep(3)
    raise TimeoutError("AssemblyAI transcription timed out")


TRANSCRIBERS = {
    "clova": transcribe_clova,
    "azure": transcribe_azure,
    "whisper": transcribe_whisper,
    "google": transcribe_google,
    "assemblyai": transcribe_assemblyai,
}


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run(manifest_path: Path, engines: list[str]) -> None:
    rows = load_manifest(manifest_path)
    long_rows: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []

    for row in rows:
        if not row.get("audio_id"):
            continue
        audio_path = ensure_audio(row)
        reference = read_reference(row)
        matrix = {
            "audio_id": row["audio_id"],
            "dataset": row.get("dataset", ""),
            "category": row.get("category", ""),
            "audio_file": display_path(audio_path),
        }
        for engine in engines:
            try:
                transcript = TRANSCRIBERS[engine](audio_path)
                scores = cer(reference, transcript)
                status = "OK"
                error_message = ""
            except Exception as exc:
                transcript = ""
                scores = {"substitution": "", "deletion": "", "insertion": "", "reference_chars": len(normalize_text(reference)), "cer": ""}
                status = "SKIPPED" if "missing" in str(exc).lower() else "ERROR"
                error_message = str(exc)
            matrix[CER_COLUMNS[engine]] = scores["cer"]
            long_rows.append({
                "audio_id": row["audio_id"],
                "dataset": row.get("dataset", ""),
                "category": row.get("category", ""),
                "audio_file": matrix["audio_file"],
                "engine": engine,
                "status": status,
                "cer": scores["cer"],
                "substitution": scores["substitution"],
                "deletion": scores["deletion"],
                "insertion": scores["insertion"],
                "reference_chars": scores["reference_chars"],
                "reference_text": reference,
                "hypothesis_text": transcript,
                "error": error_message,
            })
            print(f"{row['audio_id']} / {engine}: {status} {scores['cer']}")
        matrix_rows.append(matrix)

    average_row = {"audio_id": "AVERAGE", "dataset": "", "category": "", "audio_file": ""}
    summary_rows: list[dict[str, Any]] = []
    for engine in engines:
        values = [float(row[CER_COLUMNS[engine]]) for row in matrix_rows if row.get(CER_COLUMNS[engine]) not in ("", None)]
        average = round(sum(values) / len(values), 2) if values else ""
        average_row[CER_COLUMNS[engine]] = average
        summary_rows.append({"engine": engine, "audio_count": len(values), "average_cer": average})
    matrix_rows.append(average_row)

    write_csv(LONG_CSV, long_rows, [
        "audio_id", "dataset", "category", "audio_file", "engine", "status", "cer",
        "substitution", "deletion", "insertion", "reference_chars", "reference_text", "hypothesis_text", "error",
    ])
    write_csv(MATRIX_CSV, matrix_rows, ["audio_id", "dataset", "category", "audio_file", *[CER_COLUMNS[e] for e in engines]])
    write_csv(SUMMARY_CSV, summary_rows, ["engine", "audio_count", "average_cer"])
    print(f"wrote: {LONG_CSV}")
    print(f"wrote: {MATRIX_CSV}")
    print(f"wrote: {SUMMARY_CSV}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run STT engines and calculate per-file CER.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="CSV manifest with audio and reference transcript paths.")
    parser.add_argument("--engines", default=",".join(ENGINES), help="Comma-separated engines: clova,azure,whisper,google,assemblyai")
    args = parser.parse_args()
    engines = [engine.strip() for engine in args.engines.split(",") if engine.strip()]
    unknown = [engine for engine in engines if engine not in TRANSCRIBERS]
    if unknown:
        raise SystemExit(f"unknown engines: {', '.join(unknown)}")
    run(Path(args.manifest), engines)


if __name__ == "__main__":
    main()
