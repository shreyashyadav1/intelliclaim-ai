import { FileText, ExternalLink } from 'lucide-react';
import './SearchResults.css';

export default function SearchResults({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="search-results glass-card" id="search-results-panel">
      <h4 className="search-results-title">Source Documents</h4>
      <div className="search-results-list">
        {sources.map((src, i) => (
          <div key={i} className="search-result-item">
            <div className="search-result-header">
              <FileText size={14} />
              <span className="search-result-name">{src.filename || src.doc_id}</span>
              <span className="search-result-score">{((src.score || 0) * 100).toFixed(0)}% match</span>
            </div>
            {src.text_snippet && (
              <p className="search-result-snippet">{src.text_snippet}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
