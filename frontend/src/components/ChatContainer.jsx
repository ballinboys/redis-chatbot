import { useState, useEffect } from 'react';
import { authAPI, chatAPI } from '../services/api';
import MessageList from './MessageList';
import MessageInput from './MessageInput';

export default function ChatContainer({ username, onLogout }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => {
    return localStorage.getItem('session_id') || null;
  });

  // Load chat history on mount
  useEffect(() => {
    const loadHistory = async () => {
      if (sessionId) {
        try {
          const response = await chatAPI.getHistory(sessionId);
          setMessages(response.data.messages || []);
        } catch (err) {
          console.error('Failed to load history:', err);
        }
      }
    };
    loadHistory();
  }, [sessionId]);

  const handleSend = async (message) => {
    // Add user message immediately
    const userMsg = { role: 'user', content: message };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const response = await chatAPI.sendMessage(message, sessionId);
      const data = response.data;

      // Save session ID
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id);
        localStorage.setItem('session_id', data.session_id);
      }

      // Add bot response
      const botMsg = {
        role: 'assistant',
        content: data.answer,
        download_url: data.download_url,
        preview: data.preview,
        file: data.file,
        route: data.route
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      console.error('Failed to send message:', err);
      const errorMsg = {
        role: 'assistant',
        content: err.response?.data?.detail || 'Sorry, something went wrong. Please try again.'
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await authAPI.logout();
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('username');
      localStorage.removeItem('session_id');
      onLogout();
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <div>
            <h1 className="font-semibold text-gray-800">Drive Chatbot</h1>
            <p className="text-xs text-gray-500">Logged in as {username}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition"
        >
          Logout
        </button>
      </div>

      {/* Messages */}
      <MessageList messages={messages} />

      {/* Typing Indicator */}
      {loading && (
        <div className="px-4 py-2">
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <div className="flex gap-1">
              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
            <span>Bot is typing...</span>
          </div>
        </div>
      )}

      {/* Input */}
      <MessageInput onSend={handleSend} disabled={loading} />
    </div>
  );
}
