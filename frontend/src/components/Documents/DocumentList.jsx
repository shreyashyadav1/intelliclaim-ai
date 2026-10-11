import { useEffect, useRef, useState } from 'react';
import { Brain, DatabaseZap, FileImage, FileText, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatDate, formatFileSize, humanize } from '../../utils/format';
import Badge from '../Shared/Badge';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './DocumentList.css';

function sentenceCase(value) {
  const text = humanize(value);
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

/** Second step of a delete: names the document and waits for an explicit confirmation. */
function ConfirmDelete({ doc, onConfirm, onCancel }) {
  const confirmRef = useRef(null);
  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  return (
    <div
      className="document-confirm"
      role="group"
      aria-label={`Delete ${doc.filename}?`}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onCancel();
      }}
    >
      <span className="document-confirm-text">Delete this document and its search index entries?</span>
      <button ref={confirmRef} type="button" className="btn btn-danger btn-sm" onClick={onConfirm}>
        Delete
      </button>
      <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel}>
        Keep
      </button>
    </div>
  );
}

function DocumentRow({ doc, busyAction, indexed, onView, onDelete, onExtract, onIndex }) {
  const [confirming, setConfirming] = useState(false);
  const deleteRef = useRef(null);
  const failed = doc.processing_status === 'failed';
  const processed = doc.processing_status === 'processed';
  const Icon = doc.file_type === 'image' ? FileImage : FileText;

  const cancelDelete = () => {
    setConfirming(false);
    requestAnimationFrame(() => deleteRef.current?.focus());
  };

  return (
    <li className={`document-row ${failed ? 'document-row--failed' : ''}`} id={`doc-${doc.id}`}>
      <Icon size={20} className="document-row-icon" aria-hidden="true" />
      <div className="document-row-main">
        <h3 className="document-row-name">
          <button
            type="button"
            className="document-row-open"
            onClick={() => onView(doc)}
            aria-label={`View ${doc.filename}`}
            id={`view-${doc.id}`}
            translate="no"
            title={doc.filename}
          >
            {doc.filename}
          </button>
        </h3>
        <div className="document-row-tags">
          {failed ? (
            <Badge variant="danger">Processing failed</Badge>
          ) : (
            <Badge>{sentenceCase(doc.document_class) || 'Unclassified'}</Badge>
          )}
          {!failed && !processed && <Badge variant="pending">{sentenceCase(doc.processing_status)}</Badge>}
          {indexed && <Badge variant="success">Indexed</Badge>}
        </div>
        {failed && (
          <p className="document-row-error">{doc.error_message || 'The document could not be processed.'}</p>
        )}
      </div>
      <p className="document-row-meta tabular">
        <span>{doc.file_type ? doc.file_type.toUpperCase() : 'File'}, {formatFileSize(doc.file_size)}</span>
        <span>{formatDate(doc.created_at)}</span>
      </p>
      {confirming ? (
        <ConfirmDelete
          doc={doc}
          onConfirm={() => {
            setConfirming(false);
            onDelete(doc);
          }}
          onCancel={cancelDelete}
        />
      ) : (
        <div className="document-row-actions">
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            onClick={() => onExtract(doc)}
            disabled={!processed || Boolean(busyAction)}
            title={processed ? 'Extract claim data' : 'Only processed documents can be extracted'}
            aria-label={`Extract claim data from ${doc.filename}`}
            id={`extract-${doc.id}`}
          >
            {busyAction === 'extracting'
              ? <Loader2 size={16} className="spin" aria-hidden="true" />
              : <Brain size={16} aria-hidden="true" />}
            Extract
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            onClick={() => onIndex(doc)}
            disabled={!processed || Boolean(busyAction)}
            title={processed ? 'Index for AI search' : 'Only processed documents can be indexed'}
            aria-label={`Index ${doc.filename} for search`}
            id={`index-${doc.id}`}
          >
            {busyAction === 'indexing'
              ? <Loader2 size={16} className="spin" aria-hidden="true" />
              : <DatabaseZap size={16} aria-hidden="true" />}
            Index
          </button>
          <button
            ref={deleteRef}
            type="button"
            className="icon-btn icon-btn--danger"
            onClick={() => setConfirming(true)}
            disabled={Boolean(busyAction)}
            title="Delete"
            aria-label={`Delete ${doc.filename}`}
            id={`delete-${doc.id}`}
          >
            <Trash2 size={16} aria-hidden="true" />
          </button>
        </div>
      )}
    </li>
  );
}

export default function DocumentList({
  documents,
  total,
  error,
  onRetry,
  busy = {},
  indexedIds,
  indexingAll = false,
  onView,
  onDelete,
  onExtract,
  onIndex,
  onIndexAll,
}) {
  let content;
  if (error) {
    content = <ErrorState title="Couldn't load documents" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!documents) {
    content = <LoadingState label="Loading documents…" />;
  } else if (documents.length === 0) {
    content = (
      <EmptyState icon={FileText} title="No documents yet">
        Upload a PDF or scan above. Its text is read with OCR and classified, then you can extract the claim.
      </EmptyState>
    );
  } else {
    content = (
      <ul className="document-rows" role="list">
        {documents.map((doc) => (
          <DocumentRow
            key={doc.id}
            doc={doc}
            busyAction={busy[doc.id]}
            indexed={indexedIds?.has(doc.id) ?? false}
            onView={onView}
            onDelete={onDelete}
            onExtract={onExtract}
            onIndex={onIndex}
          />
        ))}
      </ul>
    );
  }

  return (
    <section className="document-list" id="document-list" aria-labelledby="document-list-title">
      <div className="section-head">
        <h2 id="document-list-title">Documents{documents ? ` (${total ?? documents.length})` : ''}</h2>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onIndexAll}
          disabled={indexingAll || !documents?.length}
          title="Rebuild the AI search index from every processed document"
          id="index-all-btn"
        >
          <RefreshCw size={14} className={indexingAll ? 'spin' : ''} aria-hidden="true" />
          {indexingAll ? 'Re-indexing…' : 'Re-index all'}
        </button>
      </div>
      {content}
      {documents && total > documents.length && (
        <p className="document-list-footnote">
          Showing the {documents.length} most recent of {total} documents.
        </p>
      )}
    </section>
  );
}
