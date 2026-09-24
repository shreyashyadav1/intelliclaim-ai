import { Brain, Eye, FileText, Image, Loader, Trash2 } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatDate, formatFileSize, humanize } from '../../utils/format';
import Badge from '../Shared/Badge';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './DocumentList.css';

const CLASS_BADGES = {
  medical_report: 'info',
  invoice: 'warning',
  claim_form: 'success',
  discharge_summary: 'pending',
};

function DocumentCard({ doc, busyAction, onView, onDelete, onExtract }) {
  const failed = doc.processing_status === 'failed';
  const processed = doc.processing_status === 'processed';

  return (
    <div className={`document-card glass-card ${failed ? 'document-card--failed' : ''}`} id={`doc-${doc.id}`}>
      <div className="document-card-icon">
        {doc.file_type === 'image' ? <Image size={24} /> : <FileText size={24} />}
      </div>
      <div className="document-card-info">
        <h4 className="document-card-name" title={doc.filename}>{doc.filename}</h4>
        <div className="document-card-meta">
          {failed ? (
            <Badge variant="danger">Processing failed</Badge>
          ) : (
            <Badge variant={CLASS_BADGES[doc.document_class] ?? 'info'}>
              {humanize(doc.document_class) || 'unclassified'}
            </Badge>
          )}
          {!failed && !processed && <Badge variant="pending">{humanize(doc.processing_status)}</Badge>}
          <span className="document-card-size">{formatFileSize(doc.file_size)}</span>
          <span className="document-card-date">{formatDate(doc.created_at)}</span>
        </div>
        {failed && (
          <p className="document-card-error">{doc.error_message || 'The document could not be processed.'}</p>
        )}
      </div>
      <div className="document-card-actions">
        <button
          className="doc-action-btn"
          onClick={() => onView(doc)}
          title="View"
          aria-label={`View ${doc.filename}`}
          id={`view-${doc.id}`}
        >
          <Eye size={16} />
        </button>
        <button
          className="doc-action-btn doc-action-btn--accent"
          onClick={() => onExtract(doc)}
          disabled={!processed || Boolean(busyAction)}
          title={processed ? 'Extract claim data' : 'Only processed documents can be extracted'}
          aria-label={`Extract claim data from ${doc.filename}`}
          id={`extract-${doc.id}`}
        >
          {busyAction === 'extracting' ? <Loader size={16} className="doc-action-spinner" /> : <Brain size={16} />}
        </button>
        <button
          className="doc-action-btn doc-action-btn--danger"
          onClick={() => onDelete(doc)}
          disabled={Boolean(busyAction)}
          title="Delete"
          aria-label={`Delete ${doc.filename}`}
          id={`delete-${doc.id}`}
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}

export default function DocumentList({ documents, total, error, onRetry, busy = {}, onView, onDelete, onExtract }) {
  let content;
  if (error) {
    content = (
      <div className="glass-card document-list-state">
        <ErrorState title="Couldn't load documents" message={getErrorMessage(error)} onRetry={onRetry} />
      </div>
    );
  } else if (!documents) {
    content = (
      <div className="glass-card document-list-state">
        <LoadingState label="Loading documents…" />
      </div>
    );
  } else if (documents.length === 0) {
    content = (
      <div className="glass-card document-list-state">
        <EmptyState icon={FileText} title="No documents yet">
          Upload a PDF or image above to run OCR and classification.
        </EmptyState>
      </div>
    );
  } else {
    content = (
      <div className="document-grid">
        {documents.map((doc) => (
          <DocumentCard
            key={doc.id}
            doc={doc}
            busyAction={busy[doc.id]}
            onView={onView}
            onDelete={onDelete}
            onExtract={onExtract}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="document-list" id="document-list">
      <div className="document-list-header">
        <h3>Documents{documents ? ` (${total ?? documents.length})` : ''}</h3>
      </div>
      {content}
      {documents && total > documents.length && (
        <p className="document-list-footnote">
          Showing the {documents.length} most recent of {total} documents.
        </p>
      )}
    </div>
  );
}
