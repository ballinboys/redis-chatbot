import { useEffect, useRef, useState } from 'react';

export default function ChatMessage({ message }) {
  const messageRef = useRef(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const isUser = message.role === 'user';

  useEffect(() => {
    if (messageRef.current) {
      messageRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [message]);

  // Truncate content if too long
  const MAX_PREVIEW_LENGTH = 150;
  const content = message.content || '';
  const isLongContent = content.length > MAX_PREVIEW_LENGTH;
  const displayContent = isLongContent && !isExpanded
    ? content.substring(0, MAX_PREVIEW_LENGTH) + '...'
    : content;

  return (
    <div ref={messageRef} className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-br-md'
            : 'bg-gray-100 text-gray-800 rounded-bl-md'
        }`}
      >
        {!isUser && (
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <span className="text-xs font-medium text-gray-600">Bot</span>
          </div>
        )}

        <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {displayContent}
        </div>

        {/* Expand/Collapse button for long content */}
        {isLongContent && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className={`mt-2 text-xs font-medium underline ${
              isUser ? 'text-white/80 hover:text-white' : 'text-blue-600 hover:text-blue-700'
            }`}
          >
            {isExpanded ? 'Tutup' : 'Lihat Selengkapnya'}
          </button>
        )}

        {message.download_url && (
          <a
            href={message.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-flex items-center gap-2 bg-white/20 hover:bg-white/30 rounded-lg px-3 py-2 transition"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            <span className="text-sm font-medium">Download File</span>
          </a>
        )}

        {message.preview && (
          <div className="mt-2 p-3 bg-black/5 rounded-lg">
            <p className="text-xs font-medium mb-1">Preview:</p>
            <p className="text-xs whitespace-pre-wrap">
              {isExpanded
                ? message.preview.text || 'Tidak ada preview'
                : (message.preview.text?.substring(0, 100) || 'Tidak ada preview') + '...'
              }
            </p>
            {message.preview.text && message.preview.text.length > 100 && !isExpanded && (
              <button
                onClick={() => setIsExpanded(true)}
                className="mt-1 text-xs text-blue-600 hover:text-blue-700 underline"
              >
                Lihat Preview Lengkap
              </button>
            )}
          </div>
        )}

        {message.file && (
          <div className="mt-2 text-xs opacity-75">
            📎 {message.file.name}
          </div>
        )}
      </div>
    </div>
  );
}
