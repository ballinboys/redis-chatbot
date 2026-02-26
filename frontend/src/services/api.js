import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('username');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  register: (username, password, email) =>
    api.post('/api/auth/register', { username, password, email }),
  login: (username, password) =>
    api.post('/api/auth/login', { username, password }),
  logout: () =>
    api.post('/api/auth/logout'),
  getMe: () =>
    api.get('/api/auth/me'),
};

// Chat API
export const chatAPI = {
  sendMessage: (message, sessionId) =>
    api.post('/api/chat', { message, session_id: sessionId }),
  getHistory: (sessionId) =>
    api.get(`/api/session/history?session_id=${sessionId}`),
};

export default api;
