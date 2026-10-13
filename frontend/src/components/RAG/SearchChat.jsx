import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Bot, FileText, RefreshCw, Send, Sparkles, User } from 'lucide-react';
import { getErrorMessage, ragApi } from '../../services/api';
import MockBadge from '../Shared/MockBadge';
import './SearchChat.css';

const suggestedQuestions = [
  'What was the diagnosis in Claim CLM-2026-10004?',
  'Show all claims involving knee surgery',
  'What is the total cost of claims from Metro General Hospital?',
  'List patients with treatment costs over $50,000',
];

const MESSAGE_ICONS = { user: User, assistant: Bot, error: AlertCircle };

function formatMatch(score) {
  const clamped = Math.min(Math.max(Number(score) || 0, 0), 1);
  return `${(clamped * 100).toFixed(0)}%`;
}

function ChatMessage({ message, onRetry, disabled }) {
  const Icon = MESSAGE_ICONS[message.role];
  const variant = message.role === 'user' ? 'user' : 'assistant';

  return (
    <div className={`chat-message chat-message--${variant} ${message.role === 'error' ? 'chat-message--error' : ''}`}>
      <div className="chat-message-avatar">
        <Icon size={16} />
      </div>
      <div className="chat-message-content" role={message.role === 'error' ? 'alert' : undefined}>
        {message.role === 'error' && <p className="chat-error-title">The search failed</p>}
        <p>{message.content}</p>

        {message.role === 'error' && (
          <button type="button" className="chat-retry-btn" onClick={() => onRetry(message.question)} disabled={disabled}>
            <RefreshCw size={12} /> Try again
          </button>
        )}

        {message.role === 'assistant' && message.source === 'mock' && (
          <div className="chat-message-meta">
            <MockBadge source={message.source} />
          </div>
        )}

        {message.sources?.length > 0 && (
          <div className="chat-sources">
            <span className="chat-sources-label">Sources:</span>
            {message.sources.map((src, index) => (
              <div key={index} className="chat-source-item" title={src.text_snippet}>
                <FileText size={12} />
                <span className="chat-source-name">{src.filename || src.doc_id}</span>
                <span className="chat-source-score">{formatMatch(src.score)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SearchChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const ask = async (text) => {
    const question = text.trim();
    if (!question || loading) return;

    setMessages((current) => [...current, { role: 'user', content: question }]);
    setInput('');
    setLoading(true);

    try {
      const result = await ragApi.query(question);
      setMessages((current) => [...current, {
        role: 'assistant',
        content: result.answer || 'The search service returned an empty answer.',
        sources: result.sources ?? result.source_documents ?? [],
        source: result.source,
      }]);
    } catch (err) {
      setMessages((current) => [...current, { role: 'error', content: getErrorMessage(err), question }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    ask(input);
  };

  return (
    <div className="search-chat" id="rag-search-chat">
      {messages.length === 0 ? (
        <div className="search-chat-empty">
          <div className="search-chat-empty-icon">
            <Sparkles size={36} />
          </div>
          <h3>Ask about your claims</h3>
          <p>Use natural language to search across all indexed claim documents</p>
          <div className="suggested-questions">
            {suggestedQuestions.map((question, index) => (
              <button
                key={question}
                type="button"
                className="suggested-btn"
                onClick={() => ask(question)}
                id={`suggested-q-${index}`}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="search-chat-messages" role="log" aria-live="polite">
          {messages.map((message, index) => (
            <ChatMessage key={index} message={message} onRetry={ask} disabled={loading} />
          ))}
          {loading && (
            <div className="chat-message chat-message--assistant">
              <div className="chat-message-avatar"><Bot size={16} /></div>
              <div className="chat-message-content">
                <div className="typing-indicator" role="status" aria-label="Searching documents">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      <form className="search-chat-input-wrapper" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Ask about your claims..."
          aria-label="Ask a question about your claims"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={loading}
          className="search-chat-input"
          id="rag-search-input"
        />
        <button
          type="submit"
          className="search-chat-send"
          disabled={loading || !input.trim()}
          aria-label="Send question"
          id="rag-send-btn"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
