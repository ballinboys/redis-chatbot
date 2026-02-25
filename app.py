import io
import os
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import google.generativeai as genai

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from pypdf import PdfReader

load_dotenv()
app = FastAPI()

# ===== ENV =====
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Recommended for deploy: store the whole service account JSON in env
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

# Optional local fallback:
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

FOLDER_ID = (os.getenv("GOOGLE_DRIVE_FOLDER_ID") or "").strip()

# Optional: set in deploy to your public domain. If empty, we'll infer from request.
BASE_URL_ENV = (os.getenv("BASE_URL") or "").rstrip("/")

if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY in .env / env vars")

# ===== Gemini =====
genai.configure(api_key=GEMINI_API_KEY)

# Put your preferred model first. We'll fallback automatically if not available.
GEMINI_MODEL_CANDIDATES =  "models/gemini-2.5-flash"


SYSTEM_PROMPT = """
Kamu adalah router perintah untuk sistem dokumen internal.
Ubah perintah user menjadi JSON ketat (tanpa markdown, tanpa teks lain).

Skema JSON wajib:
{
  "action": "download" | "preview",
  "query": "kata kunci pencarian file",
  "category": "proposal" | "cv" | "other"
}

Aturan:
- "ambil", "download", "kirim file", "minta pdf" => action="download"
- "lihat", "preview", "tampilkan isi", "baca" => action="preview"
- query singkat & relevan untuk nama file (contoh: "proposal", "cv gregorius")
- category:
  - jika mengandung "proposal" => proposal
  - jika mengandung "cv" atau "resume" => cv
  - selain itu => other
Kembalikan JSON saja.
"""

def gemini_route(user_text: str) -> Dict[str, Any]:
    model = genai.GenerativeModel(
        model_name="models/gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT
    )

    resp = model.generate_content(user_text)
    raw = (resp.text or "").strip()

    try:
        data = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(500, f"Gemini returned non-JSON: {raw}")
        data = json.loads(raw[start:end + 1])

    if data.get("action") not in ("download", "preview"):
        raise HTTPException(500, f"Invalid action from Gemini: {data}")
    if not data.get("query"):
        raise HTTPException(500, f"Empty query from Gemini: {data}")
    if data.get("category") not in ("proposal", "cv", "other"):
        data["category"] = "other"

    return data


# ===== Drive client (Service Account) =====
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

def build_drive_service():
    # Preferred: read service account JSON from env
    if SERVICE_ACCOUNT_JSON:
        try:
            info = json.loads(SERVICE_ACCOUNT_JSON)
        except Exception as e:
            raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}")

        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("drive", "v3", credentials=creds), creds.service_account_email

    # Local fallback: read from file
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise RuntimeError(
            "Missing credentials. Provide GOOGLE_SERVICE_ACCOUNT_JSON (recommended) "
            f"or ensure {SERVICE_ACCOUNT_FILE} exists."
        )

    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build("drive", "v3", credentials=creds), creds.service_account_email


drive, SA_EMAIL = build_drive_service()

def _in_folder_clause() -> str:
    return f" and '{FOLDER_ID}' in parents" if FOLDER_ID else ""

def drive_search(query: str, topn: int = 10) -> List[Dict[str, Any]]:
    # NOTE: only files shared to service account will appear
    q = (
        f"name contains '{query}'"
        + _in_folder_clause() +
        " and trashed=false"
        " and mimeType != 'application/vnd.google-apps.folder'"
        " and (mimeType='application/pdf' or mimeType='application/vnd.google-apps.document')"
    )
    res = drive.files().list(
        q=q,
        fields="files(id,name,mimeType,modifiedTime,webViewLink)",
        pageSize=min(max(topn, 1), 50),
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return res.get("files", [])

def _download_pdf_or_export(file_id: str) -> tuple[bytes, str]:
    meta = drive.files().get(
        fileId=file_id,
        fields="name,mimeType",
        supportsAllDrives=True
    ).execute()

    name = meta["name"]
    mime = meta["mimeType"]

    if mime == "application/pdf":
        request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        filename = name if name.lower().endswith(".pdf") else f"{name}.pdf"
    elif mime == "application/vnd.google-apps.document":
        request = drive.files().export_media(fileId=file_id, mimeType="application/pdf")
        filename = f"{name}.pdf"
    else:
        raise HTTPException(400, f"Unsupported mimeType: {mime}")

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return fh.getvalue(), filename

def preview_text(file_id: str, pages: int = 3, max_chars: int = 4000) -> Dict[str, Any]:
    file_bytes, _ = _download_pdf_or_export(file_id)
    reader = PdfReader(io.BytesIO(file_bytes))
    parts: List[str] = []
    for p in reader.pages[:max(1, pages)]:
        parts.append(p.extract_text() or "")
    text = "\n".join(parts).strip()
    if not text:
        return {"warning": "Teks tidak terbaca (kemungkinan PDF scan). Perlu OCR untuk preview.", "text": ""}
    return {"text": text[:max_chars]}

def resolve_base_url(request: Request) -> str:
    # Use env if provided; otherwise infer from incoming request (works in deploy)
    if BASE_URL_ENV:
        return BASE_URL_ENV
    return str(request.base_url).rstrip("/")

def build_download_url(request: Request, file_id: str) -> str:
    base = resolve_base_url(request)
    return f"{base}/drive/download/{file_id}"


# ===== HTTP endpoints =====
@app.get("/health")
def health():
    return {
        "ok": True,
        "service_account_email": SA_EMAIL,
        "folder_restriction": bool(FOLDER_ID),
        "base_url_env_set": bool(BASE_URL_ENV),
    }

@app.get("/drive/download/{file_id}")
def http_download(file_id: str):
    data, filename = _download_pdf_or_export(file_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

class ChatPayload(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatPayload, request: Request):
    user_text = (req.message or "").strip()
    if not user_text:
        raise HTTPException(400, "message is required")

    route = gemini_route(user_text)  # {action, query, category, _model_used}

    q = route["query"]
    # perketat query berdasarkan category
    if route["category"] == "proposal" and "proposal" not in q.lower():
        q = "proposal " + q
    if route["category"] == "cv" and "cv" not in q.lower():
        q = "cv " + q

    results = drive_search(q, topn=5)
    if not results:
        # fallback: query kategori saja
        fallback_q = route["category"] if route["category"] != "other" else route["query"]
        results = drive_search(fallback_q, topn=5)

    if not results:
        return {
            "answer": (
                f"Tidak ketemu file untuk '{route['query']}'. "
                f"Pastikan file sudah dishare ke service account: {SA_EMAIL}"
            ),
            "route": route,
            "results": []
        }

    picked = results[0]
    file_id = picked["id"]

    if route["action"] == "download":
        url = build_download_url(request, file_id)
        return {
            "answer": f"Ini link downloadnya: {url}",
            "download_url": url,
            "file": picked,
            "route": route
        }

    prev = preview_text(file_id)
    return {
        "answer": prev.get("warning") or "Berikut preview isi (potongan):",
        "preview": prev,
        "file": picked,
        "route": route
    }