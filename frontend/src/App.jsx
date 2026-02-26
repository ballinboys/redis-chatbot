import { useState, useEffect } from 'react';
import { authAPI } from './services/api';
import LoginForm from './components/LoginForm';
import ChatContainer from './components/ChatContainer';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token');
      const savedUsername = localStorage.getItem('username');

      if (token && savedUsername) {
        try {
          await authAPI.getMe();
          setUsername(savedUsername);
          setIsAuthenticated(true);
        } catch (err) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('username');
        }
      }
      setLoading(false);
    };

    checkAuth();
  }, []);

  const handleLoginSuccess = () => {
    const savedUsername = localStorage.getItem('username');
    setUsername(savedUsername);
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setUsername('');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600">
        <div className="w-16 h-16 border-4 border-white border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return isAuthenticated ? (
    <ChatContainer username={username} onLogout={handleLogout} />
  ) : (
    <LoginForm onSuccess={handleLoginSuccess} />
  );
}

export default App;
