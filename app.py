import io
import os
import json
import re
import uuid
import hashlib
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import redis

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from pypdf import PdfReader

load_dotenv()
app = FastAPI()

# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== ENV =====
# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False
    print("Warning: Redis not available, falling back to in-memory storage")

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ===== REDIS SESSION STORE =====
class RedisSessionStore:
    """Redis-based session storage with in-memory fallback"""

    def __init__(self):
        self.use_redis = REDIS_AVAILABLE
        self.in_memory: Dict[str, Dict] = {}
        self.session_timeout = 3600 * 24  # 24 hours

    def _redis_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def create_session(self, user_id: str = None) -> str:
        """Create new session and return session_id"""
        session_id = str(uuid.uuid4())
        session_data = {
            "created_at": datetime.now().isoformat(),
            "user_id": user_id,
            "messages": [],
            "context": {},
            "last_activity": datetime.now().isoformat()
        }

        if self.use_redis:
            redis_client.setex(
                self._redis_key(session_id),
                self.session_timeout,
                json.dumps(session_data)
            )
        else:
            self.in_memory[session_id] = session_data

        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data if exists and not expired"""
        if self.use_redis:
            data = redis_client.get(self._redis_key(session_id))
            if not data:
                return None
            return json.loads(data)
        else:
            session = self.in_memory.get(session_id)
            if not session:
                return None

            # Check timeout
            last_activity = datetime.fromisoformat(session["last_activity"])
            if datetime.now() - last_activity > timedelta(seconds=self.session_timeout):
                del self.in_memory[session_id]
                return None

            return session

    def update_session(self, session_id: str, **kwargs):
        """Update session data"""
        session = self.get_session(session_id)
        if session:
            session.update(kwargs)
            session["last_activity"] = datetime.now().isoformat()

            if self.use_redis:
                redis_client.setex(
                    self._redis_key(session_id),
                    self.session_timeout,
                    json.dumps(session)
                )

    def add_message(self, session_id: str, role: str, content: str, route: Dict = None):
        """Add message to chat history"""
        session = self.get_session(session_id)
        if session:
            session["messages"].append({
                "role": role,
                "content": content,
                "route": route,
                "timestamp": datetime.now().isoformat()
            })

            if self.use_redis:
                redis_client.setex(
                    self._redis_key(session_id),
                    self.session_timeout,
                    json.dumps(session)
                )

    def get_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get recent chat history"""
        session = self.get_session(session_id)
        if session:
            return session["messages"][-limit:]
        return []

    def set_context(self, session_id: str, key: str, value: Any):
        """Store context data (e.g., pending file options)"""
        session = self.get_session(session_id)
        if session:
            session["context"][key] = value

            if self.use_redis:
                redis_client.setex(
                    self._redis_key(session_id),
                    self.session_timeout,
                    json.dumps(session)
                )

    def get_context(self, session_id: str, key: str) -> Any:
        """Get context data"""
        session = self.get_session(session_id)
        if session:
            return session["context"].get(key)
        return None

    def clear_context(self, session_id: str, key: str = None):
        """Clear specific or all context"""
        session = self.get_session(session_id)
        if session:
            if key:
                session["context"].pop(key, None)
            else:
                session["context"] = {}

            if self.use_redis:
                redis_client.setex(
                    self._redis_key(session_id),
                    self.session_timeout,
                    json.dumps(session)
                )

    def delete_session(self, session_id: str):
        """Delete a session"""
        if self.use_redis:
            redis_client.delete(self._redis_key(session_id))
        else:
            self.in_memory.pop(session_id, None)


# Global session store
session_store = RedisSessionStore()


# ===== USER MANAGEMENT =====
class UserStore:
    """User management with Redis backend"""

    def __init__(self):
        self.use_redis = REDIS_AVAILABLE
        self.in_memory: Dict[str, Dict] = {}

    def _redis_key(self, username: str) -> str:
        return f"user:{username}"

    def create_user(self, username: str, password: str, email: str = None) -> bool:
        """Create a new user"""
        if self.user_exists(username):
            return False

        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user_data = {
            "username": username,
            "password_hash": password_hash,
            "email": email,
            "created_at": datetime.now().isoformat()
        }

        if self.use_redis:
            redis_client.set(self._redis_key(username), json.dumps(user_data))
        else:
            self.in_memory[username] = user_data

        return True

    def user_exists(self, username: str) -> bool:
        """Check if user exists"""
        if self.use_redis:
            return redis_client.exists(self._redis_key(username))
        else:
            return username in self.in_memory

    def verify_user(self, username: str, password: str) -> bool:
        """Verify user credentials"""
        if self.use_redis:
            data = redis_client.get(self._redis_key(username))
            if not data:
                return False
            user_data = json.loads(data)
        else:
            user_data = self.in_memory.get(username)
            if not user_data:
                return False

        # Verify password
        return bcrypt.checkpw(password.encode('utf-8'), user_data["password_hash"].encode('utf-8'))

    def get_user(self, username: str) -> Optional[Dict]:
        """Get user data without password"""
        if self.use_redis:
            data = redis_client.get(self._redis_key(username))
            if not data:
                return None
            user_data = json.loads(data)
        else:
            user_data = self.in_memory.get(username)
            if not user_data:
                return None

        # Return without password
        return {
            "username": user_data["username"],
            "email": user_data.get("email"),
            "created_at": user_data["created_at"]
        }


# Global user store
user_store = UserStore()


# ===== AUTHENTICATION =====
def create_access_token(username: str) -> str:
    """Create JWT access token"""
    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> Optional[str]:
    """Verify JWT token and return username"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("username")
    except jwt.PyJWTError:
        return None


async def get_current_user(authorization: str = Header(None)) -> Optional[str]:
    """Get current user from Authorization header"""
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        return None

    token = authorization.split(" ")[1]
    username = verify_access_token(token)

    return username


# Pydantic models for auth
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

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
  "query": "kata kunci pencarian file yang bersih (hanya kata kunci penting, tanpa filler)",
  "category": "proposal" | "cv" | "other" | "any",
  "response": "jawaban chat sederhana (untuk action=chat)"
}

Aturan ACTION (deteksi berdasarkan intent, bukan kata persis):
- Download: download, ambil, kirim, minta, request, can i get, give me
- Read/Preview: baca, lihat, tampilkan, preview, isi, show, open, check (file content)
- Summarize: summary, summarize, ringkas, rangkum, singkat,简述, tinjau
- Check/Search: ada, punya, ada nggak, apakah ada, berapa, cari, carikan, carikan saya, search, find, do you have, is there, exist
- Chat: selain yang di atas, beri response membantu

QUERY EXTRACTION (PENTING):
- Extract hanya kata kunci bernilai untuk pencarian file
- Hilangkan filler: yang, ya, kan, dong, deh, nih, toh, kok, sih, lah, cuma, aja, nya, dengan, buat, atau, dan, berapa, saya
- Contoh:
  * "ambil cv dong" => query: "cv"
  * "apakah ada cv?" => query: "cv"
  * "berapa cv consultant?" => query: "cv consultant"
  * "cari cv gregorius" => query: "cv gregorius"
  * "carikan saya proposal" => query: "proposal"
  * "download proposal yang kemarin" => query: "proposal kemarin"
  * "baca isi cv gregorius" => query: "cv gregorius"

Category berdasarkan konteks:
- mengandung "proposal" => proposal
- mengandung "cv", "resume", "curriculum vitae" => cv
- lainnya => other

Untuk action="chat", beri response yang membantu jelaskan fitur yang tersedia:
"Maaf, saya belum bisa menjawab pertanyaan tersebut. Saat ini saya bisa membantu:
📁 Cek file - 'apakah ada cv/proposal?'
🔍 Cari file - 'cari cv gregorius'
📖 Baca isi - 'baca cv gregorius'
📝 Summary - 'ringkas proposal'
⬇️ Download - 'download cv'"

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

    # Check/Search intent (include "cari", "carikan")
    if any(word in text_lower for word in ["ada", "punya", "punya nggak", "apakah", "cari", "carikan", "carikan saya"]):
        query = extract_query(user_text)
        category = categorize_query(query) if query else "any"
        return {"action": "check", "query": query, "category": category, "response": ""}

    # Download intent
    if any(word in text_lower for word in ["download", "ambil", "kirim", "minta"]):
        return {"action": "download", "query": extract_query(user_text), "category": categorize_query(user_text), "response": ""}

    # Read/preview intent
    if any(word in text_lower for word in ["baca", "lihat", "tampilkan", "preview", "isi"]):
        return {"action": "read", "query": extract_query(user_text), "category": categorize_query(user_text), "response": ""}

    # Summarize intent (include "ringkas")
    if any(word in text_lower for word in ["summary", "summarize", "ringkasan", "rangkum", "ringkas", "singkat"]):
        return {"action": "summarize", "query": extract_query(user_text), "category": categorize_query(user_text), "response": ""}

    # Default chat
    return {"action": "chat", "query": "", "category": "any", "response": ""}


def extract_query(text: str) -> str:
    """Extract meaningful keywords from user message for file search"""
    import re

    # Common action words to remove
    action_words = {
        "download", "ambil", "kirim", "minta", "baca", "lihat", "tampilkan",
        "preview", "isi", "summary", "summarize", "ringkasan", "rangkum",
        "ringkas", "singkat", "ada", "punya", "apakah", "file", "dokumen",
        "cari", "carikan", "search", "find"
    }

    # Indonesian filler particles (short, non-meaningful words)
    filler_particles = {
        "yang", "ya", "kan", "dong", "deh", "nih", "toh", "kok", "sih",
        "lah", "cuma", "aja", "nya", "dengan", "buat", "atau", "dan", "berapa", "saya"
    }

    text_lower = text.lower()
    words = text_lower.split()

    # Filter words: keep only meaningful keywords
    keywords = []
    for word in words:
        # Remove punctuation from word
        clean_word = re.sub(r'[^\w-]', '', word)

        # Skip if empty, action word, or single-letter filler
        if not clean_word or len(clean_word) <= 1:
            continue
        if clean_word in action_words or clean_word in filler_particles:
            continue
        if clean_word in {"nggak", "gak", "enggak", "tidak"}:
            continue

        keywords.append(clean_word)

    return " ".join(keywords)


def categorize_query(text: str) -> str:
    """Categorize query into proposal/cv/other"""
    text_lower = text.lower()
    if "proposal" in text_lower:
        return "proposal"
    elif any(word in text_lower for word in ["cv", "resume", "curriculum"]):
        return "cv"
    return "other"


def detect_number_selection(user_text: str, max_number: int) -> Optional[int]:
    """Detect if user is selecting a number from a list

    Returns:
        int: The selected number (1-indexed), or None if not a selection
    """
    text_lower = user_text.lower()
    words = text_lower.split()

    # Check for number words (first, second, third, etc.)
    number_words = {
        "pertama": 1, "satu": 1, "one": 1, "1": 1,
        "kedua": 2, "dua": 2, "two": 2, "2": 2,
        "ketiga": 3, "tiga": 3, "three": 3, "3": 3,
        "keempat": 4, "empat": 4, "four": 4, "4": 4,
        "kelima": 5, "lima": 5, "five": 5, "5": 5,
        "keenam": 6, "enam": 6, "six": 6, "6": 6,
    }

    # Check if user said a number word
    for word in words:
        clean = re.sub(r'[^\w]', '', word)
        if clean in number_words:
            num = number_words[clean]
            return num if num <= max_number else None

    # Check for standalone numbers
    for word in words:
        if word.isdigit():
            num = int(word)
            if 1 <= num <= max_number:
                return num

    return None


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

    # Aggressive text cleaning for PDF output
    # 1. Fix hyphenated words at line breaks
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)

    # 2. Remove excessive spaces (2+ spaces become 1)
    text = re.sub(r' {2,}', ' ', text)

    # 3. Fix newlines - single newlines become spaces, double newlines become paragraph breaks
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)  # Single newline -> space
    text = re.sub(r'\n {2,}', '\n', text)       # Remove leading spaces after newline
    text = re.sub(r' {2,}\n', '\n', text)       # Remove trailing spaces before newline

    # 4. Fix multiple spaces that might have been created
    text = re.sub(r' +', ' ', text)

    # 5. Fix paragraph breaks (3+ newlines -> 2 newlines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 6. Clean up URLs at the end (put each URL on new line)
    text = re.sub(r'(https?://\S+)', r'\n\1', text)

    # 7. Final cleanup - trim whitespace
    text = text.strip()

    return {"text": text[:max_chars]}

def resolve_base_url(request: Request) -> str:
    # Use env if provided; otherwise infer from incoming request (works in deploy)
    if BASE_URL_ENV:
        return BASE_URL_ENV.strip().rstrip("/")

    # For Vercel/serverless, build from headers
    # Try to get the actual host from the request
    scheme = request.url.scheme
    host = request.headers.get("host", request.headers.get("x-forwarded-host", request.url.hostname))

    # Build the base URL
    if host:
        return f"{scheme}://{host}"
    else:
        # Fallback to request.base_url
        return str(request.base_url).rstrip("/")

def build_download_url(request: Request, file_id: str) -> str:
    base = resolve_base_url(request)
    return f"{base}/api/drive/download/{file_id}"


# ===== HTTP endpoints =====
@app.get("/health")
def health():
    return {
        "ok": True,
        "service_account_email": SA_EMAIL,
        "folder_restriction": bool(FOLDER_ID),
        "base_url_env_set": bool(BASE_URL_ENV),
        "redis_available": REDIS_AVAILABLE
    }


# ===== Authentication Endpoints =====
@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register a new user"""
    username = req.username.strip()
    password = req.password

    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")

    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    if user_store.create_user(username, password, req.email):
        return {
            "success": True,
            "message": "User registered successfully",
            "username": username
        }
    else:
        raise HTTPException(400, "Username already exists")


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login and get access token"""
    username = req.username.strip()
    password = req.password

    if user_store.verify_user(username, password):
        access_token = create_access_token(username)
        return {
            "success": True,
            "access_token": access_token,
            "token_type": "bearer",
            "username": username
        }
    else:
        raise HTTPException(401, "Invalid username or password")


@app.post("/api/auth/logout")
async def logout(current_user: str = Depends(get_current_user)):
    """Logout (client-side token removal)"""
    return {
        "success": True,
        "message": "Logged out successfully"
    }


@app.get("/api/auth/me")
async def get_me(current_user: str = Depends(get_current_user)):
    """Get current user info"""
    user_data = user_store.get_user(current_user)
    if user_data:
        return {
            "success": True,
            "user": user_data
        }
    else:
        raise HTTPException(404, "User not found")


@app.get("/api/session/history")
async def get_chat_history(
    session_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get chat history for a session"""
    history = session_store.get_history(session_id, limit=100)
    return {
        "success": True,
        "session_id": session_id,
        "messages": history
    }

@app.get("/api/drive/download/{file_id}")
async def http_download(file_id: str, current_user: str = Depends(get_current_user)):
    data, filename = _download_pdf_or_export(file_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

class ChatPayload(BaseModel):
    message: str
    session_id: Optional[str] = None  # Optional session ID for conversation memory

@app.post("/api/chat")
async def chat(req: ChatPayload, request: Request, current_user: str = Depends(get_current_user)):
    # ===== SESSION HANDLING =====
    session_id = req.session_id
    session = None

    if session_id:
        session = session_store.get_session(session_id)

    # Create new session if doesn't exist
    if not session:
        session_id = session_store.create_session()
        session = session_store.get_session(session_id)

    user_text = (req.message or "").strip()

    # Check if user is responding to a file selection prompt
    pending_files = session_store.get_context(session_id, "pending_file_selection")
    pending_action = session_store.get_context(session_id, "pending_action")

    if pending_files and pending_action:
        # User is selecting from previous file list
        selection = detect_number_selection(user_text, len(pending_files))

        if selection:
            # User selected a file number
            selected_file = pending_files[selection - 1]
            file_id = selected_file["id"]

            # Clear the pending context
            session_store.clear_context(session_id)

            # Execute the pending action
            if pending_action == "download":
                url = build_download_url(request, file_id)
                response = {
                    "answer": f"Oke, ini link download untuk '{selected_file['name']}': {url}",
                    "download_url": url,
                    "file": selected_file,
                    "route": {"action": "download", "query": "", "category": "any"}
                }
            elif pending_action == "read":
                prev = preview_text(file_id, pages=5, max_chars=8000)
                response = {
                    "answer": prev.get("warning") or f"Berikut isi dari '{selected_file['name']}' (potongan):",
                    "preview": prev,
                    "file": selected_file,
                    "route": {"action": "read", "query": "", "category": "any"}
                }
            elif pending_action == "summarize":
                prev = preview_text(file_id, pages=3, max_chars=4000)
                response = {
                    "answer": f"Summary dari '{selected_file['name']}':",
                    "preview": prev,
                    "file": selected_file,
                    "route": {"action": "summarize", "query": "", "category": "any"}
                }
            else:
                response = {
                    "answer": "Maaf, ada error internal.",
                    "route": {"action": "error", "query": "", "category": "any"}
                }

            # Add to history
            session_store.add_message(session_id, "user", user_text)
            session_store.add_message(session_id, "assistant", response["answer"], response.get("route"))
            response["session_id"] = session_id
            return response

    # Normal message flow
    if not user_text:
        response = {
            "answer": "Halo! Saya chatbot dokumen. Ada yang bisa dibantu?",
            "route": {"action": "chat", "query": "", "category": "any"},
            "session_id": session_id
        }
        session_store.add_message(session_id, "assistant", response["answer"], response["route"])
        return response

    # Simple greeting check (no API call)
    text_lower = user_text.lower()
    simple_greetings = ["hai", "halo", "hello", "hi", "hey", "selamat pagi", "selamat siang", "selamat sore", "selamat malam"]

    if any(greeting in text_lower for greeting in simple_greetings):
        response = {
            "answer": "Halo! Saya chatbot dokumen Anda. Saya bisa bantu cek file, baca isi, summarize, atau download file dari Google Drive. Ada yang bisa dibantu?",
            "route": {"action": "greeting", "query": "", "category": "any"},
            "session_id": session_id
        }
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", response["answer"], response["route"])
        return response

    # Route using Claude (or simple fallback)
    route = await claude_route(user_text)

    # Handle simple chat (not document related)
    if route["action"] == "chat":
        response_text = route.get("response") or """Maaf, saya belum bisa menjawab pertanyaan tersebut. Saat ini saya bisa membantu Anda dengan:

📁 **Cek file** - "apakah ada cv/proposal?"
📖 **Baca isi** - "baca cv gregorius"
📝 **Summary** - "ringkas proposal"
⬇️ **Download** - "download cv consultant"

Silakan coba dengan format pertanyaan di atas!"""
        response = {
            "answer": response_text,
            "route": route,
            "session_id": session_id
        }
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", response["answer"], route)
        return response

    # Build search query
    q = route["query"]
    if route["category"] == "proposal" and "proposal" not in q.lower():
        q = "proposal " + q
    elif route["category"] == "cv" and "cv" not in q.lower():
        q = "cv " + q
    elif q == "":
        q = route["category"] if route["category"] != "any" else ""

    # Special case for check action with no query - search by category
    if route["action"] == "check" and not q:
        q = route["category"] if route["category"] != "any" else ""

    # Search files
    try:
        results = drive_search(q, topn=5) if q else []
    except Exception as e:
        response = {
            "answer": f"Maaf, ada error saat mencari file: {str(e)}",
            "route": route,
            "results": [],
            "session_id": session_id
        }
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", response["answer"], route)
        return response

    # Handle "check" action - just verify files exist
    if route["action"] == "check":
        session_store.add_message(session_id, "user", user_text)
        if results:
            file_names = [f["name"] for f in results[:5]]
            answer = f"Ya, ada {len(results)} file yang ditemukan: {', '.join(file_names)}"
            response = {
                "answer": answer,
                "route": route,
                "results": results,
                "count": len(results),
                "session_id": session_id
            }
            session_store.add_message(session_id, "assistant", answer, route)
            return response
        else:
            # Better message when no files found
            query_display = route["query"] or route["category"]
            answer = f"Maaf, tidak ada file untuk '{query_display}'. Pastikan file sudah dishare ke service account: {SA_EMAIL}"
            response = {
                "answer": answer,
                "route": route,
                "results": [],
                "count": 0,
                "session_id": session_id
            }
            session_store.add_message(session_id, "assistant", answer, route)
            return response

    # No files found for other actions
    if not results:
        answer = f"Tidak ketemu file untuk '{route['query']}'. Pastikan file sudah dishare ke service account: {SA_EMAIL}"
        response = {
            "answer": answer,
            "route": route,
            "results": [],
            "session_id": session_id
        }
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", answer, route)
        return response

    # Check for multiple files - ask user to select for download/read/summarize
    if len(results) > 1:
        # Check if first 2 files have same name (case-insensitive)
        first_name_lower = results[0]["name"].lower()
        same_name_count = sum(1 for f in results if f["name"].lower() == first_name_lower)

        if same_name_count >= 2:
            # Multiple files with exact same name - store context and ask user to select
            file_list = "\n".join([f"{i+1}. {f['name']}" for i, f in enumerate(results[:5])])

            # Store pending selection in session
            session_store.set_context(session_id, "pending_file_selection", results[:5])
            session_store.set_context(session_id, "pending_action", route["action"])

            answer = f"Ditemukan {len(results)} file. Mau yang mana?\n{file_list}\n\nBalas dengan nomor (1-{len(results)}) atau 'yang pertama/kedua/...'"

            session_store.add_message(session_id, "user", user_text)
            session_store.add_message(session_id, "assistant", answer, route)

            return {
                "answer": answer,
                "route": route,
                "results": results,
                "need_clarification": True,
                "options": [{"id": f["id"], "name": f["name"], "modified": f.get("modifiedTime")} for f in results[:5]],
                "session_id": session_id
            }

    # For download/read/summarize - just pick the first result
    picked = results[0]
    file_id = picked["id"]

    # Download action
    if route["action"] == "download":
        url = build_download_url(request, file_id)
        answer = f"Ini link download untuk file '{picked['name']}': {url}"
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", answer, route)
        return {
            "answer": answer,
            "download_url": url,
            "file": picked,
            "route": route,
            "session_id": session_id
        }

    # Read action - show more content
    if route["action"] == "read":
        prev = preview_text(file_id, pages=5, max_chars=8000)
        answer = prev.get("warning") or f"Berikut isi dari '{picked['name']}' (potongan):"
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", answer, route)
        return {
            "answer": answer,
            "preview": prev,
            "file": picked,
            "route": route,
            "session_id": session_id
        }

    # Summarize action - show preview with summary label
    if route["action"] == "summarize":
        prev = preview_text(file_id, pages=3, max_chars=4000)
        answer = f"Summary dari '{picked['name']}':"
        session_store.add_message(session_id, "user", user_text)
        session_store.add_message(session_id, "assistant", answer, route)
        return {
            "answer": answer,
            "preview": prev,
            "file": picked,
            "route": route,
            "session_id": session_id
        }

    # Fallback
    answer = "Maaf, fitur ini belum tersedia."
    session_store.add_message(session_id, "user", user_text)
    session_store.add_message(session_id, "assistant", answer, route)
    return {
        "answer": answer,
        "route": route,
        "session_id": session_id
    }