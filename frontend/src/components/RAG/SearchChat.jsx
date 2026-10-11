import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { getErrorMessage, ragApi } from '../../services/api';
import MockBadge from '../Shared/MockBadge';
import './SearchChat.css';

const suggestedQuestions = [
  'Which patients were treated at Metro General Hospital?',
  'What did the knee replacement claims cost?',
  'List claims with treatment costs over $50,000',
  'Which claims were for pneumonia, and where were they treated?',
];

const prefersReducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches);

function formatMatch(score) {
  const clamped = Math.min(Math.max(Number(score) || 0, 0), 1);
  return `${(clamped * 100).toFixed(0)}%`;
}

const SNIPPET_PREVIEW_LINES = 4;

function Citation({ src }) {
  const [expanded, setExpanded] = useState(false);
  const snippet = src.text_snippet ?? '';
  const long = snippet.split('\n').length > SNIPPET_PREVIEW_LINES || snippet.length > 220;

  return (
    <li className="citation">
      <div className="citation-head">
        <span className="citation-name" translate="no">{src.filename || src.doc_id}</span>
        <span className="citation-score">
          <span className="tabular">{formatMatch(src.score)}</span> match
        </span>
        {src.doc_id && (
          <Link to={`/documents?doc=${encodeURIComponent(src.doc_id)}`} className="text-link citation-open">
            Open document
          </Link>
        )}
      </div>
      {snippet && (
        <blockquote className="citation-snippet" data-clamped={(long && !expanded) || undefined}>
          {snippet}
        </blockquote>
      )}
      {long && (
        <button type="button" className="citation-toggle" aria-expanded={expanded} onClick={() => setExpanded((open) => !open)}>
          {expanded ? 'Show less of the passage' : 'Show the whole passage'}
        </button>
      )}
    </li>
  );
}

function Citations({ sources }) {
  return (
    <div className="citations">
      <h3 className="citations-title">Sources</h3>
      <ol className="citations-list">
        {sources.map((src, index) => <Citation key={`${src.doc_id}-${index}`} src={src} />)}
      </ol>
    </div>
  );
}

function Exchange({ exchange, onRetry, disabled }) {
  const { question, status, answer, error } = exchange;
  return (
    <article className="exchange" aria-label={question}>
      <p className="exchange-question">{question}</p>

      {status === 'loading' && (
        <p className="exchange-pending" role="status">
          <Loader2 size={16} className="spin" aria-hidden="true" />
          Searching the indexed documents…
        </p>
      )}

      {status === 'error' && (
        <div className="exchange-error" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <div>
            <p className="exchange-error-title">The search failed</p>
            <p>{error}</p>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onRetry(exchange)} disabled={disabled}>
              <RefreshCw size={14} aria-hidden="true" /> Try again
            </button>
          </div>
        </div>
      )}

      {status === 'done' && (
        <div className="exchange-answer">
          <p className="exchange-answer-label">
            Answer <MockBadge source={answer.source} />
          </p>
          <p className="exchange-answer-text">{answer.content}</p>
          {answer.sources.length > 0 && <Citations sources={answer.sources} />}
        </div>
      )}
    </article>
  );
}

export default function SearchChat() {
  const [exchanges, setExchanges] = useState([]);
  const [input, setInput] = useState('');
  const loading = exchanges.some((exchange) => exchange.status === 'loading');
  const endRef = useRef(null);
  const nextId = useRef(0);

  useEffect(() => {
    if (exchanges.length === 0) return;
    endRef.current?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'end' });
  }, [exchanges]);

  const run = async (id, question) => {
    try {
      const result = await ragApi.query(question);
      const answer = {
        content: result.answer || 'The search service returned an empty answer.',
        sources: result.sources ?? result.source_documents ?? [],
        source: result.source,
      };
      setExchanges((current) => current.map((item) => (item.id === id ? { ...item, status: 'done', answer } : item)));
    } catch (err) {
      setExchanges((current) => current.map((item) => (
        item.id === id ? { ...item, status: 'error', error: getErrorMessage(err) } : item
      )));
    }
  };

  const ask = (text) => {
    const question = text.trim();
    if (!question || loading) return;
    nextId.current += 1;
    const id = nextId.current;
    setExchanges((current) => [...current, { id, question, status: 'loading' }]);
    setInput('');
    run(id, question);
  };

  const retry = (exchange) => {
    if (loading) return;
    setExchanges((current) => current.map((item) => (
      item.id === exchange.id ? { ...item, status: 'loading', error: null } : item
    )));
    run(exchange.id, exchange.question);
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    ask(input);
  };

  return (
    <div className="search-chat" id="rag-search-chat">
      {exchanges.length === 0 ? (
        <div className="search-intro">
          <p className="search-intro-text">
            Questions are answered from the text of indexed documents, and every answer lists the passages it used.
            Index documents from the Documents page first.
          </p>
          <h2 className="search-intro-title">Try one of these</h2>
          <ul className="suggested-questions" role="list">
            {suggestedQuestions.map((question, index) => (
              <li key={question}>
                <button type="button" className="suggested-btn" onClick={() => ask(question)} id={`suggested-q-${index}`}>
                  {question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="search-transcript" role="log" aria-live="polite" aria-label="Questions and answers">
          {exchanges.map((exchange) => (
            <Exchange key={exchange.id} exchange={exchange} onRetry={retry} disabled={loading} />
          ))}
          <div ref={endRef} />
        </div>
      )}

      <form className="search-composer" onSubmit={handleSubmit}>
        <input
          type="text"
          name="question"
          autoComplete="off"
          placeholder="Ask about patients, diagnoses, hospitals or amounts…"
          aria-label="Ask a question about your claims"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={loading}
          className="search-composer-input"
          id="rag-search-input"
        />
        <button type="submit" className="btn btn-primary search-composer-send" disabled={loading || !input.trim()} id="rag-send-btn">
          {loading && <Loader2 size={16} className="spin" aria-hidden="true" />}
          Ask
        </button>
      </form>
    </div>
  );
}
