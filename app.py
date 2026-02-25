import io
import os
import json
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import httpx

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from pypdf import PdfReader

load_dotenv()
app = FastAPI()

# ===== ENV =====
# Claude API Key
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "").strip()

# Recommended for deploy: store the whole service account JSON in env
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

# Optional local fallback:
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

FOLDER_ID = (os.getenv("GOOGLE_DRIVE_FOLDER_ID") or "").strip()

# Optional: set in deploy to your public domain. If empty, we'll infer from request.
BASE_URL_ENV = (os.getenv("BASE_URL") or "").strip().rstrip("/")

# ===== Claude Haiku API =====
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """
Kamu adalah router perintah untuk chatbot dokumen Google Drive.
Analisis intent user dan kembalikan JSON ketat (tanpa markdown, tanpa teks lain).

Skema JSON:
{
  "action": "download" | "read" | "summarize" | "check" | "chat",
  "query": "kata kunci pencarian file (jika relevan)",
  "category": "proposal" | "cv" | "other" | "any",
  "response": "jawaban chat sederhana (untuk action=chat)"
}

Aturan:
- "download", "ambil", "kirim", "mintalah file" => action="download"
- "baca", "lihat", "tampilkan", "preview", "isi" => action="read"
- "summary", "summarize", "ringkasan", "rangkum" => action="summarize"
- "ada", "punya", "punya nggak", "apakah ada" => action="check"
- untuk perintah tidak terkait dokumen => action="chat", beri response ramah
- query: kata kunci untuk pencarian file
- category: "proposal", "cv", atau "other" berdasarkan kata kunci

Kembalikan JSON saja.
"""

async def claude_route(user_text: str) -> Dict[str, Any]:
    """Route user query using Claude Haiku API"""
    if not CLAUDE_API_KEY:
        # Fallback to simple pattern matching
        return simple_route(user_text)

    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_text}]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(CLAUDE_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

            raw = result.get("content", [{}])[0].get("text", "").strip()

            # Parse JSON from response
            try:
                data = json.loads(raw)
            except Exception:
                start = raw.find("{")
                end = raw.rfind("}")
                if start == -1 or end == -1:
                    return {"action": "chat", "response": f"Halo! Saya chatbot dokumen. Ada yang bisa dibantu?"}
                data = json.loads(raw[start:end + 1])

            # Validate and set defaults
            if data.get("action") not in ("download", "read", "summarize", "check", "chat"):
                data["action"] = "chat"
            if "query" not in data:
                data["query"] = ""
            if "category" not in data:
                data["category"] = "any"
            if "response" not in data:
                data["response"] = ""

            return data

    except Exception as e:
        # Fallback to simple routing
        return simple_route(user_text)


def simple_route(user_text: str) -> Dict[str, Any]:
    """Simple pattern-based routing as fallback"""
    text_lower = user_text.lower()

    # Check intent
    if any(word in text_lower for word in ["ada", "punya", "punya nggak", "apakah ada"]):
        return {"action": "check", "query": extract_query(user_text), "category": "any", "response": ""}

    # Download intent
    if any(word in text_lower for word in ["download", "ambil", "kirim", "minta"]):
        return {"action": "download", "query": extract_query(user_text), "category": categorize_query(user_text), "response": ""}

    # Read/preview intent
    if any(word in text_lower for word in ["baca", "lihat", "tampilkan", "preview", "isi"]):
        return {"action": "read", "query": extract_query(user_text), "category": categorize_query(user_text), "response": ""}

    # Summarize intent
    if any(word in text_lower for word in ["summary", "summarize", "ringkasan", "rangkum"]):
        return {"action": "summarize", "query": extract_query(user_text), "category": categorize_query(user_text), "response": ""}

    # Default chat
    return {"action": "chat", "query": "", "category": "any", "response": ""}


def extract_query(text: str) -> str:
    """Extract file search query from user message"""
    # Remove common action words
    text = text.lower()
    remove_words = ["download", "ambil", "kirim", "minta", "baca", "lihat", "tampilkan", "preview", "isi",
                   "summary", "summarize", "ringkasan", "rangkum", "ada", "punya", "punya nggak", "apakah ada",
                   "file", "yang", "dong", "ya", "deh", "nih"]

    for word in remove_words:
        text = text.replace(word, "")

    return text.strip()


def categorize_query(text: str) -> str:
    """Categorize query into proposal/cv/other"""
    text_lower = text.lower()
    if "proposal" in text_lower:
        return "proposal"
    elif any(word in text_lower for word in ["cv", "resume", "curriculum"]):
        return "cv"
    return "other"


# ===== Drive client (Service Account) =====
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

def build_drive_service():
    # Try environment variable first (recommended for Vercel/deployments)
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    # Fallback to local file for development
    if not sa_json:
        sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
        if os.path.exists(sa_file):
            with open(sa_file, "r") as f:
                sa_json = f.read()

    if not sa_json:
        raise RuntimeError(
            "Missing Google credentials. Please set GOOGLE_SERVICE_ACCOUNT_JSON environment variable."
        )

    try:
        info = json.loads(sa_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON format: {e}")

    # Validate required fields
    required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
    missing_fields = [f for f in required_fields if f not in info]
    if missing_fields:
        raise RuntimeError(f"Missing required fields in service account JSON: {missing_fields}")

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)
    return drive, info.get("client_email")


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
        return BASE_URL_ENV.strip().rstrip("/")
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
async def chat(req: ChatPayload, request: Request):
    user_text = (req.message or "").strip()
    if not user_text:
        return {
            "answer": "Halo! Saya chatbot dokumen. Ada yang bisa dibantu?",
            "route": {"action": "chat", "query": "", "category": "any"}
        }

    # Simple greeting check (no API call)
    text_lower = user_text.lower()
    simple_greetings = ["hai", "halo", "hello", "hi", "hey", "selamat pagi", "selamat siang", "selamat sore", "selamat malam"]

    if any(greeting in text_lower for greeting in simple_greetings):
        return {
            "answer": "Halo! Saya chatbot dokumen Anda. Saya bisa bantu cek file, baca isi, summarize, atau download file dari Google Drive. Ada yang bisa dibantu?",
            "route": {"action": "greeting", "query": "", "category": "any"}
        }

    # Route using Claude (or simple fallback)
    route = await claude_route(user_text)

    # Handle simple chat (not document related)
    if route["action"] == "chat":
        response = route.get("response") or "Maaf, fitur ini belum tersedia. Saya cuma bisa bantu urusan dokumen: cek file, baca, summarize, dan download."
        return {
            "answer": response,
            "route": route
        }

    # Build search query
    q = route["query"]
    if route["category"] == "proposal" and "proposal" not in q.lower():
        q = "proposal " + q
    elif route["category"] == "cv" and "cv" not in q.lower():
        q = "cv " + q
    elif q == "":
        q = route["category"] if route["category"] != "any" else ""

    # Search files
    try:
        results = drive_search(q, topn=5) if q else []
    except Exception as e:
        return {
            "answer": f"Maaf, ada error saat mencari file: {str(e)}",
            "route": route,
            "results": []
        }

    # Handle "check" action - just verify files exist
    if route["action"] == "check":
        if results:
            file_names = [f["name"] for f in results[:5]]
            return {
                "answer": f"Ya, ada {len(results)} file yang ditemukan: {', '.join(file_names)}",
                "route": route,
                "results": results,
                "count": len(results)
            }
        else:
            return {
                "answer": f"Maaf, tidak ada file untuk '{route['query']}'. Pastikan file sudah dishare ke service account: {SA_EMAIL}",
                "route": route,
                "results": [],
                "count": 0
            }

    # No files found for other actions
    if not results:
        return {
            "answer": f"Tidak ketemu file untuk '{route['query']}'. Pastikan file sudah dishare ke service account: {SA_EMAIL}",
            "route": route,
            "results": []
        }

    # Check for multiple files with same or similar names
    if len(results) > 1:
        # Check if first 2 files have same name (case-insensitive)
        first_name_lower = results[0]["name"].lower()
        same_name_count = sum(1 for f in results if f["name"].lower() == first_name_lower)

        if same_name_count >= 2:
            # Multiple files with exact same name - ask user to specify
            file_list = "\n".join([f"{i+1}. {f['name']} (Modified: {f.get('modifiedTime', 'N/A')})" for i, f in enumerate(results[:5])])
            return {
                "answer": f"Ditemukan {len(results)} file dengan nama mirip. Mau yang mana?\n{file_list}\n\nSilakan spesifikasikan lebih detail (misal: tambahkan tanggal atau detail lain).",
                "route": route,
                "results": results,
                "need_clarification": True,
                "options": [{"id": f["id"], "name": f["name"], "modified": f.get("modifiedTime")} for f in results[:5]]
            }

    picked = results[0]
    file_id = picked["id"]

    # Download action
    if route["action"] == "download":
        url = build_download_url(request, file_id)
        return {
            "answer": f"Ini link download untuk file '{picked['name']}': {url}",
            "download_url": url,
            "file": picked,
            "route": route
        }

    # Read action - show more content
    if route["action"] == "read":
        prev = preview_text(file_id, pages=5, max_chars=8000)
        return {
            "answer": prev.get("warning") or f"Berikut isi dari '{picked['name']}' (potongan):",
            "preview": prev,
            "file": picked,
            "route": route
        }

    # Summarize action - show preview with summary label
    if route["action"] == "summarize":
        prev = preview_text(file_id, pages=3, max_chars=4000)
        return {
            "answer": f"Summary dari '{picked['name']}':",
            "preview": prev,
            "file": picked,
            "route": route
        }

    # Fallback
    return {
        "answer": "Maaf, fitur ini belum tersedia.",
        "route": route
    }