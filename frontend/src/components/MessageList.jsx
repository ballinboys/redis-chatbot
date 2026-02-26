import { useEffect, useRef } from 'react';
import ChatMessage from './ChatMessage';

export default function MessageList({ messages }) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full mx-auto mb-4 flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-800 mb-2">Welcome to Drive Chatbot!</h3>
            <p className="text-gray-500 text-sm">
              I can help you search, read, and download files from Google Drive.
              <br /><br />
              Try asking:
            </p>
            <div className="mt-4 space-y-2 text-sm">
              <div className="bg-gray-100 rounded-lg px-4 py-2 text-gray-700">
                "Check if there are any CVs"
              </div>
              <div className="bg-gray-100 rounded-lg px-4 py-2 text-gray-700">
                "Search for proposal"
              </div>
              <div className="bg-gray-100 rounded-lg px-4 py-2 text-gray-700">
                "Read the CV Gregorius"
              </div>
            </div>
          </div>
        </div>
      ) : (
        messages.map((msg, index) => (
          <ChatMessage key={index} message={msg} />
        ))
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}
