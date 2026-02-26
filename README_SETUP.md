# Drive Chatbot with React + Redis + Auth

Full-stack chatbot application with React frontend, FastAPI backend, Redis session storage, and multi-user authentication.

## Features

- 🎨 **Modern React UI** - Beautiful chat interface with Tailwind CSS
- 🔐 **Multi-user Authentication** - Register/Login with JWT tokens
- 📝 **Chat History** - Redis-powered session memory across requests
- 📁 **Google Drive Integration** - Search, read, summarize, and download files
- 💬 **Smart Chat** - Claude Haiku-powered intent recognition

## Project Structure

```
chat-ambildata/
├── app.py                 # FastAPI backend
├── requirements.txt       # Python dependencies
├── vercel.json           # Deployment config
├── .env.example          # Environment variables template
└── frontend/             # React frontend
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css
        ├── components/
        │   ├── LoginForm.jsx
        │   ├── ChatContainer.jsx
        │   ├── MessageList.jsx
        │   ├── MessageInput.jsx
        │   └── ChatMessage.jsx
        └── services/
            └── api.js
```

## Local Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- Redis server (or use [Upstash](https://upstash.com/) for cloud Redis)

### 1. Backend Setup

```bash
# Navigate to project directory
cd chat-ambildata

# Install Python dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env

# Edit .env and add your values:
# - CLAUDE_API_KEY
# - GOOGLE_SERVICE_ACCOUNT_JSON
# - JWT_SECRET
# - REDIS_URL (redis://localhost:6379 for local)
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Copy environment variables
cp .env.example .env

# For local development, leave VITE_API_URL empty
```

### 3. Start Redis (Local)

```bash
# Using Docker
docker run -d -p 6379:6379 redis

# Or install Redis locally
# macOS: brew install redis && brew services start redis
# Ubuntu: sudo apt install redis-server && sudo systemctl start redis
```

### 4. Run Development Servers

**Terminal 1 - Backend:**
```bash
cd chat-ambildata
uvicorn app:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd chat-ambildata/frontend
npm run dev
```

Visit `http://localhost:3000` and register/login!

## Production Deployment (Vercel)

### 1. Prepare Redis (Upstash)

1. Go to [Upstash](https://upstash.com/) and create a free account
2. Create a new Redis database
3. Copy the Redis URL (format: `rediss://default:xxx@xxx.upstash.io:6379`)

### 2. Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Login to Vercel
vercel login

# Deploy from project root
cd chat-ambildata
vercel
```

### 3. Set Environment Variables in Vercel

Go to your Vercel dashboard → Project Settings → Environment Variables and add:

```
CLAUDE_API_KEY=your_key
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
JWT_SECRET=your_random_secret_string
REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379
PYTHON_VERSION=3.12
```

### 4. Redeploy

After setting environment variables, redeploy:
```bash
vercel --prod
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get token
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Get current user info

### Chat
- `POST /api/chat` - Send chat message
- `GET /api/session/history?session_id=xxx` - Get chat history

### Files
- `GET /api/drive/download/{file_id}` - Download file from Drive

### Health
- `GET /health` - Health check

## Features Usage

### Chat Commands

- **Check files**: "Ada CV nggak?", "Cari proposal"
- **Read content**: "Baca CV Gregorius", "Lihat isi proposal"
- **Download**: "Download CV consultant", "Ambil proposal"
- **Summarize**: "Ringkas CV", "Summary proposal"

### Session Memory

The bot remembers your conversation across requests using Redis:
- File selections from search results
- Chat history
- Context for follow-up questions

Example:
```
You: Cari CV
Bot: Found 5 CVs. Which one?
  1. CV Andi
  2. CV Budi
  3. CV Citra
You: Yang nomor 2
Bot: [Displays CV Budi content]
```

## Troubleshooting

### Redis Connection Error
- Check if Redis is running: `redis-cli ping`
- Verify REDIS_URL in .env
- For Upstash, ensure URL starts with `rediss://` (SSL)

### CORS Error
- Check vercel.json routes configuration
- Ensure API routes start with `/api/`

### Auth Error (401)
- Clear localStorage and login again
- Check JWT_SECRET is set correctly
- Verify token hasn't expired (24h default)

### Frontend Build Issues
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

## License

MIT
