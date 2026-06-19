import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, FileText } from 'lucide-react';
import { ragApi } from '../../services/api';
import './SearchChat.css';

const suggestedQuestions = [
  "What was the diagnosis in Claim CLM-2026-10004?",
  "Show all claims involving knee surgery",
  "What is the total cost of claims from Metro General Hospital?",
  "List patients with treatment costs over $50,000",
];

const demoResponses = {
  default: {
    answer: "Based on the indexed documents, I found relevant information across multiple claims. The claim CLM-2026-10004 involves a Lumbar Disc Herniation (M51.16) for patient James Williams, with a treatment cost of $67,200 at Spine Care Institute. This claim has been flagged for review due to high treatment cost exceeding the $50,000 threshold.",
    sources: [
      { doc_id: 'doc-4', filename: 'discharge_summary_williams.pdf', text_snippet: 'Patient: James Williams, Diagnosis: Lumbar Disc Herniation...', score: 0.94 },
      { doc_id: 'doc-1', filename: 'medical_report_johnson.pdf', text_snippet: 'ACL reconstruction surgery performed on 05/28/2026...', score: 0.72 },
    ],
  },
};

export default function SearchChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text) => {
    const question = text || input.trim();
    if (!question) return;

    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setInput('');
    setLoading(true);

    try {
      const result = await ragApi.query(question);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.answer,
        sources: result.sources || result.source_documents,
      }]);
    } catch {
      // Use demo response
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: demoResponses.default.answer,
        sources: demoResponses.default.sources,
      }]);
    } finally {
      setLoading(false);
    }
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
            {suggestedQuestions.map((q, i) => (
              <button key={i} className="suggested-btn" onClick={() => sendMessage(q)} id={`suggested-q-${i}`}>
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="search-chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`chat-message chat-message--${msg.role}`}>
              <div className="chat-message-avatar">
                {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
              </div>
              <div className="chat-message-content">
                <p>{msg.content}</p>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="chat-sources">
                    <span className="chat-sources-label">Sources:</span>
                    {msg.sources.map((src, j) => (
                      <div key={j} className="chat-source-item">
                        <FileText size={12} />
                        <span className="chat-source-name">{src.filename || src.doc_id}</span>
                        <span className="chat-source-score">{((src.score || 0) * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="chat-message chat-message--assistant">
              <div className="chat-message-avatar"><Bot size={16} /></div>
              <div className="chat-message-content">
                <div className="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      <div className="search-chat-input-wrapper">
        <input
          type="text"
          placeholder="Ask about your claims..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          disabled={loading}
          className="search-chat-input"
          id="rag-search-input"
        />
        <button className="search-chat-send" onClick={() => sendMessage()} disabled={loading || !input.trim()} id="rag-send-btn">
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
