import { useEffect, useId, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Brain, DatabaseZap, Loader2, X } from 'lucide-react';
import { formatDate, formatFileSize, humanize } from '../../utils/format';
import { CLAIM_FIELDS } from '../../utils/trace';
import ExtractionResults from '../Claims/ExtractionResults';
import Badge from '../Shared/Badge';
import { LoadingState } from '../Shared/StateMessage';
import SourceDocument from '../Trace/SourceDocument';
import { useTrace } from '../Trace/useTrace';
import './DocumentViewer.css';

const FIELD_LABELS = Object.fromEntries(CLAIM_FIELDS.map((field) => [field.key, field.label]));
const STATUS_BADGES = { processed: 'success', failed: 'danger' };

function sentenceCase(value) {
  const text = humanize(value);
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

/** Keeps keyboard focus inside the sheet, closes it on Escape and restores focus on close. */
function useModalFocus(panelRef, onClose) {
  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const root = document.getElementById('root');
    root?.setAttribute('inert', '');
    document.documentElement.classList.add('has-modal');
    panelRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      root?.removeAttribute('inert');
      document.documentElement.classList.remove('has-modal');
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) previouslyFocused.focus();
    };
  }, [panelRef, onClose]);
}

function DocumentFacts({ document }) {
  const pages = Number(document.page_count);
  return (
    <dl className="doc-facts">
      <div>
        <dt>Type</dt>
        <dd>{document.file_type ? document.file_type.toUpperCase() : '—'}</dd>
      </div>
      <div>
        <dt>Size</dt>
        <dd className="tabular">{formatFileSize(document.file_size)}</dd>
      </div>
      {pages > 0 && (
        <div>
          <dt>Pages</dt>
          <dd className="tabular">{pages}</dd>
        </div>
      )}
      <div>
        <dt>Uploaded</dt>
        <dd className="tabular">{formatDate(document.created_at)}</dd>
      </div>
    </dl>
  );
}

/**
 * Review sheet for one document: the OCR text as a typed page on the left;
 * on the right the document's details, the extract action and, once
 * extracted, the fields traced back into the text.
 */
export default function DocumentViewer({
  document,
  loading,
  error,
  onRetry,
  extraction,
  extracting,
  indexing,
  indexed,
  notice,
  onClose,
  onExtract,
  onIndex,
}) {
  const panelRef = useRef(null);
  const titleId = useId();
  useModalFocus(panelRef, onClose);

  const processed = document.processing_status === 'processed';
  const text = loading || error ? null : (document.extracted_text ?? document.extracted_text_preview ?? '');
  const extracted = extraction?.extracted_data;
  const fields = useMemo(
    () => CLAIM_FIELDS.map((field) => ({ ...field, value: extracted?.[field.key] })),
    [extracted],
  );
  const { trace, activeKey, preview, locate, sheetRef } = useTrace(extracted ? text : null, fields);

  let indexLabel = 'Index for search';
  if (indexed) indexLabel = 'Indexed for search';
  else if (indexing) indexLabel = 'Indexing…';

  // Rendered into <body> so the sheet sits above the page in the top layer of the
  // stacking order, outside any transformed or scrolling page container.
  return createPortal(
    <div className="doc-sheet-backdrop" onClick={onClose}>
      <div
        ref={panelRef}
        className="doc-sheet"
        onClick={(event) => event.stopPropagation()}
        id="document-viewer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="doc-sheet-header">
          <div className="doc-sheet-title-row">
            <h2 id={titleId} className="doc-sheet-title" translate="no" title={document.filename}>{document.filename}</h2>
            <Badge>{sentenceCase(document.document_class) || 'Unclassified'}</Badge>
            <Badge variant={STATUS_BADGES[document.processing_status] ?? 'pending'}>
              {sentenceCase(document.processing_status) || 'Unknown'}
            </Badge>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} id="doc-viewer-close-btn" aria-label="Close document">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <div className="doc-sheet-body">
          <div className="doc-sheet-source">
            <SourceDocument
              document={loading ? null : document}
              loading={loading}
              error={error}
              onRetry={onRetry}
              trace={trace}
              activeKey={activeKey}
              onHover={preview}
              labels={FIELD_LABELS}
              sheetRef={sheetRef}
              headingLevel={3}
            />
          </div>

          <div className="doc-sheet-aside">
            {notice}
            <DocumentFacts document={document} />

            {extraction ? (
              <ExtractionResults
                result={extraction}
                fields={fields}
                trace={trace}
                activeKey={activeKey}
                onActivate={preview}
                onLocate={locate}
              >
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => onIndex(document)}
                  disabled={indexing || indexed}
                  id="index-extracted-btn"
                >
                  {indexing ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <DatabaseZap size={16} aria-hidden="true" />}
                  {indexLabel}
                </button>
              </ExtractionResults>
            ) : (
              <div className="doc-extract">
                <h3 className="doc-extract-title">Claim data</h3>
                <p className="doc-extract-body">
                  {processed
                    ? 'Extraction reads the eleven claim fields from this text, creates or updates the claim, and shows where each value was found.'
                    : 'Only documents whose text was read successfully can be extracted.'}
                </p>
                {extracting && <LoadingState label="Extracting claim data…" />}
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => onExtract(document)}
                  disabled={!processed || extracting}
                  id="extract-data-btn"
                >
                  {extracting ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <Brain size={16} aria-hidden="true" />}
                  {extracting ? 'Extracting…' : 'Extract claim data'}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    window.document.body,
  );
}
