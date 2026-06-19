import { X, FileText, Brain, Download } from 'lucide-react';
import Badge from '../Shared/Badge';
import './DocumentViewer.css';

export default function DocumentViewer({ document, onClose, onExtract }) {
  if (!document) return null;

  return (
    <div className="doc-viewer-overlay" onClick={onClose}>
      <div className="doc-viewer glass-card" onClick={(e) => e.stopPropagation()} id="document-viewer">
        <div className="doc-viewer-header">
          <div className="doc-viewer-title-row">
            <FileText size={18} />
            <h3>{document.filename}</h3>
            <Badge variant="info">{document.document_class?.replace(/_/g, ' ')}</Badge>
          </div>
          <button className="doc-viewer-close" onClick={onClose} id="doc-viewer-close-btn">
            <X size={20} />
          </button>
        </div>

        <div className="doc-viewer-body">
          <div className="doc-viewer-section">
            <h4>Extracted Text</h4>
            <div className="doc-viewer-text">
              {document.extracted_text || document.extracted_text_preview || 'No text extracted yet. Run OCR extraction first.'}
            </div>
          </div>

          <div className="doc-viewer-meta">
            <div className="doc-viewer-meta-item">
              <span className="doc-viewer-meta-label">File Type</span>
              <span className="doc-viewer-meta-value">{document.file_type?.toUpperCase()}</span>
            </div>
            <div className="doc-viewer-meta-item">
              <span className="doc-viewer-meta-label">Status</span>
              <Badge variant={document.processing_status === 'processed' ? 'success' : 'pending'}>
                {document.processing_status}
              </Badge>
            </div>
            <div className="doc-viewer-meta-item">
              <span className="doc-viewer-meta-label">Uploaded</span>
              <span className="doc-viewer-meta-value">
                {new Date(document.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        </div>

        <div className="doc-viewer-footer">
          <button className="btn btn-primary" onClick={() => onExtract?.(document)} id="extract-data-btn">
            <Brain size={16} /> Extract Claim Data
          </button>
        </div>
      </div>
    </div>
  );
}
