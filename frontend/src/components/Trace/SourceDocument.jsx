import { useId } from 'react';
import { FileText } from 'lucide-react';
import { humanize } from '../../utils/format';
import Badge from '../Shared/Badge';
import { ErrorState, LoadingState } from '../Shared/StateMessage';
import SourceLines from './SourceLines';
import './Trace.css';

function sentenceCase(value) {
  const text = humanize(value);
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

/** Tabs for choosing which of a claim's documents to read. */
function DocumentChooser({ documents, selectedId, onSelect }) {
  return (
    <div className="source-chooser" role="group" aria-label="Source documents">
      {documents.map((doc) => (
        <button
          key={doc.id}
          type="button"
          className="source-chooser-option"
          aria-pressed={doc.id === selectedId}
          onClick={() => onSelect(doc.id)}
          title={doc.filename}
        >
          {sentenceCase(doc.document_class) || 'Document'}
        </button>
      ))}
    </div>
  );
}

function SheetBody({ document, loading, error, onRetry, trace, activeKey, onHover, labels }) {
  if (error) {
    return <ErrorState title="Couldn't load the document text" message={error} onRetry={onRetry} />;
  }
  if (loading || !document) return <LoadingState label="Loading the document text…" />;
  if (document.processing_status === 'failed') {
    return (
      <p className="source-sheet-message">
        Text extraction failed: {document.error_message || 'the document could not be read.'}
      </p>
    );
  }
  const text = document.extracted_text ?? document.extracted_text_preview;
  if (!text) return <p className="source-sheet-message">No text was extracted from this document.</p>;

  const activeLines = activeKey ? trace?.fields[activeKey]?.lines : undefined;
  return (
    <SourceLines
      text={text}
      marks={trace?.marks}
      activeKey={activeKey}
      activeLines={activeLines}
      labels={labels}
      onHover={onHover}
    />
  );
}

/**
 * The source document as a typed page with numbered lines, its traced values
 * highlighted. Shows a chooser when a claim has several documents, and the
 * loading, error and empty states of the document text.
 */
export default function SourceDocument({
  documents,
  selectedId,
  onSelect,
  document,
  loading = false,
  error = null,
  onRetry,
  empty,
  trace,
  activeKey,
  onHover,
  labels,
  sheetRef,
}) {
  const headingId = useId();
  const filename = document?.filename;

  return (
    <section className="source-panel" aria-labelledby={headingId}>
      <div className="source-panel-head">
        <h2 id={headingId} className="source-panel-title">Source document</h2>
        {documents?.length > 1 && (
          <DocumentChooser documents={documents} selectedId={selectedId} onSelect={onSelect} />
        )}
      </div>

      {empty ? (
        <div className="source-empty">{empty}</div>
      ) : (
        <div
          ref={sheetRef}
          className="source-scroll"
          tabIndex={0}
          role="region"
          aria-label={filename ? `Text of ${filename}` : 'Document text'}
        >
          <article className="source-sheet">
            <header className="source-sheet-head">
              <FileText size={14} aria-hidden="true" />
              <span className="source-sheet-name" translate="no" title={filename}>{filename || 'Loading…'}</span>
              {document?.document_class && <Badge>{sentenceCase(document.document_class)}</Badge>}
            </header>
            <SheetBody
              document={document}
              loading={loading}
              error={error}
              onRetry={onRetry}
              trace={trace}
              activeKey={activeKey}
              onHover={onHover}
              labels={labels}
            />
          </article>
        </div>
      )}
    </section>
  );
}
