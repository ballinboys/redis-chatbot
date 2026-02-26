# Implementation Plan: Chatbot with React + Redis + Login

## Current State
- **Backend**: FastAPI Python (`app.py`)
- **Features**: Google Drive document search with in-memory session management
- **Session Store**: In-memory (SessionStore class) - needs to be upgraded to Redis
- **Frontend**: None (API only)

## Target State
- **Frontend**: React chat UI with chat-like interface
- **Backend**: FastAPI with Redis for session persistence
- **Auth**: Simple login system (username/password)
- **Features**: Chat messages with memory across sessions

## Architecture

### Backend Changes (app.py)
1. **Redis Integration**
   - Install `redis` package
   - Replace `SessionStore` class with Redis-based implementation
   - Store: messages, context, user sessions in Redis

2. **Authentication System**
   - Add `/login` endpoint
   - Add `/logout` endpoint
   - JWT token or simple session-based auth
   - Middleware to protect chat endpoint

3. **New Endpoints**
   - `POST /api/login` - Authenticate user
   - `POST /api/logout` - Logout user
   - `GET /api/session` - Get session info
   - `POST /api/chat` - Existing chat endpoint (with auth)

### Frontend Structure (React)
```
public/
  index.html
src/
  components/
    ChatContainer.jsx     - Main chat container
    MessageList.jsx       - Message display
    MessageInput.jsx      - Input field
    LoginForm.jsx         - Login form
    ChatMessage.jsx       - Individual message
  services/
    api.js                - API calls
  App.jsx                - Main app
  index.js               - Entry point
package.json
tailwind.config.js       - For styling
```

## Implementation Steps

### Step 1: Backend - Add Redis Support
- Add `redis` to requirements.txt
- Create `RedisSessionStore` class to replace in-memory store
- Add Redis connection handling with environment variables

### Step 2: Backend - Add Authentication
- Add user storage (Redis or simple dict)
- Add `/api/login` endpoint with password hashing
- Add JWT token generation/verification
- Add auth middleware to protect `/chat` endpoint

### Step 3: Frontend - Setup React Project
- Initialize React with Vite (faster than CRA)
- Setup Tailwind CSS for styling
- Create folder structure

### Step 4: Frontend - Chat Components
- `ChatContainer` - Main layout with messages
- `MessageList` - Scrollable message display
- `MessageInput` - Input field with send button
- `ChatMessage` - Individual message bubble (user/bot)

### Step 5: Frontend - Login Component
- Simple login form (username/password)
- Token storage (localStorage)
- Redirect to chat after login

### Step 6: Frontend - API Integration
- Create API service with axios/fetch
- Handle session_id persistence
- Connect chat form to backend

### Step 7: Testing & Deployment
- Test Redis connection
- Test login flow
- Test chat functionality
- Deploy to Vercel

## File Changes Summary

### Modified Files
- `app.py` - Add Redis, auth, new endpoints
- `requirements.txt` - Add redis, bcrypt, pyjwt
- `vercel.json` - May need updates for frontend build

### New Files (Backend)
- `redis_store.py` - Redis session management (optional, can be in app.py)

### New Files (Frontend)
- `frontend/package.json`
- `frontend/vite.config.js`
- `frontend/tailwind.config.js`
- `frontend/src/App.jsx`
- `frontend/src/components/*.jsx`
- `frontend/src/services/api.js`
- `frontend/index.html`

## Environment Variables (New)
```
REDIS_URL=redis://localhost:6379  # For production: Upstash Redis
JWT_SECRET=your-secret-key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-password
```

## Notes
- Redis can be self-hosted or use Upstash (free tier) for Vercel deployment
- Simple auth: single user or multi-user with stored credentials
- Frontend will be separate build, served from same Vercel project
