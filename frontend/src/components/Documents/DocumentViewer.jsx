import { useEffect } from 'react';
import { Brain, FileText, X } from 'lucide-react';
import { formatDate, humanize } from '../../utils/format';
import Badge from '../Shared/Badge';
import { LoadingState } from '../Shared/StateMessage';
import './DocumentViewer.css';

const STATUS_BADGES = { processed: 'success', failed: 'danger' };

function ExtractedText({ document, loading, error }) {
  if (document.processing_status === 'failed') {
    return (
      <div className="doc-viewer-text doc-viewer-text--error">
        {document.error_message || 'The document could not be processed.'}
      </div>
    );
  }
  if (loading) return <LoadingState label="Loading extracted text…" />;

  const text = document.extracted_text ?? document.extracted_text_preview;
  return (
    <>
      {error && <p className="doc-viewer-load-error" role="alert">Couldn&apos;t load the full text: {error}</p>}
      <div className="doc-viewer-text">{text || 'No text was extracted from this document.'}</div>
    </>
  );
}

export default function DocumentViewer({ document, loading, error, extracting, onClose, onExtract }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const processed = document.processing_status === 'processed';

  return (
    <div className="doc-viewer-overlay" onClick={onClose}>
      <div
        className="doc-viewer glass-card"
        onClick={(event) => event.stopPropagation()}
        id="document-viewer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="doc-viewer-title"
      >
        <div className="doc-viewer-header">
          <div className="doc-viewer-title-row">
            <FileText size={18} />
            <h3 id="doc-viewer-title">{document.filename}</h3>
            <Badge variant="info">{humanize(document.document_class) || 'unclassified'}</Badge>
          </div>
          <button className="doc-viewer-close" onClick={onClose} id="doc-viewer-close-btn" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="doc-viewer-body">
          <div className="doc-viewer-section">
            <h4>{document.processing_status === 'failed' ? 'Processing Error' : 'Extracted Text'}</h4>
            <ExtractedText document={document} loading={loading} error={error} />
          </div>

          <div className="doc-viewer-meta">
            <div className="doc-viewer-meta-item">
              <span className="doc-viewer-meta-label">File Type</span>
              <span className="doc-viewer-meta-value">{document.file_type?.toUpperCase() || '—'}</span>
            </div>
            <div className="doc-viewer-meta-item">
              <span className="doc-viewer-meta-label">Status</span>
              <Badge variant={STATUS_BADGES[document.processing_status] ?? 'pending'}>
                {humanize(document.processing_status) || 'unknown'}
              </Badge>
            </div>
            <div className="doc-viewer-meta-item">
              <span className="doc-viewer-meta-label">Uploaded</span>
              <span className="doc-viewer-meta-value">{formatDate(document.created_at)}</span>
            </div>
          </div>
        </div>

        <div className="doc-viewer-footer">
          <button
            className="btn btn-primary"
            onClick={() => onExtract(document)}
            disabled={!processed || extracting}
            id="extract-data-btn"
          >
            <Brain size={16} /> {extracting ? 'Extracting…' : 'Extract Claim Data'}
          </button>
        </div>
      </div>
    </div>
  );
}
