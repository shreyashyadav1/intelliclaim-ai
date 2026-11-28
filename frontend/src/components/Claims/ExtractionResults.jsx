import { Link } from 'react-router-dom';
import MockBadge from '../Shared/MockBadge';
import FieldSheet from '../Trace/FieldSheet';

/**
 * Fields returned by POST /extract/{document_id}, traced into the document
 * they came from, with follow-up actions as children.
 */
export default function ExtractionResults({ result, fields, trace, activeKey, onActivate, onLocate, children }) {
  // Share of the eleven claim fields found; confidence_score is the older name for the same value.
  const completeness = Number(result.completeness ?? result.confidence_score) || 0;

  return (
    <div className="extraction-results" id="extraction-results">
      <p className="extraction-outcome" role="status">
        <span>{result.is_new_claim ? 'Extracted into a new claim.' : 'Extracted into the existing claim.'}</span>
        <MockBadge source={result.source} />
      </p>
      {result.input_truncated && (
        <p className="extraction-note">
          The document was longer than the extractor reads, so only its first part was used.
        </p>
      )}
      <FieldSheet
        title="Extracted fields"
        headingLevel={3}
        fields={fields}
        trace={trace}
        completeness={completeness}
        activeKey={activeKey}
        onActivate={onActivate}
        onLocate={onLocate}
      />
      <div className="extraction-actions">
        {result.claim_id && (
          <Link to={`/claims/${result.claim_id}`} className="btn btn-secondary">
            View claim
          </Link>
        )}
        {children}
      </div>
    </div>
  );
}
