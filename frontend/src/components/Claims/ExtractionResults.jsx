import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, X } from 'lucide-react';
import { formatCurrency, formatDate } from '../../utils/format';
import MockBadge from '../Shared/MockBadge';
import './ExtractionResults.css';

const FIELDS = [
  { label: 'Policy Number', key: 'policy_number' },
  { label: 'Claim Number', key: 'claim_number' },
  { label: 'Patient Name', key: 'patient_name' },
  { label: 'Diagnosis', key: 'diagnosis' },
  { label: 'Treatment Cost', key: 'treatment_cost', format: formatCurrency },
  { label: 'Hospital Name', key: 'hospital_name' },
  { label: 'Hospital Address', key: 'hospital_address' },
  { label: 'Provider ID', key: 'provider_id' },
  { label: 'Service Date', key: 'date_of_service', format: formatDate },
  { label: 'Admission Date', key: 'date_of_admission', format: formatDate },
  { label: 'Discharge Date', key: 'date_of_discharge', format: formatDate },
];

function completenessColor(completeness) {
  if (completeness > 0.8) return 'var(--status-success)';
  if (completeness > 0.5) return 'var(--status-warning)';
  return 'var(--status-danger)';
}

/** Fields returned by POST /extract/{document_id}, with follow-up actions as children. */
export default function ExtractionResults({ document, result, onDismiss, children }) {
  const panelRef = useRef(null);
  const data = result.extracted_data ?? {};
  // Share of the eleven claim fields found; confidence_score is the older name for the same value.
  const completeness = Number(result.completeness ?? result.confidence_score) || 0;

  useEffect(() => {
    panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, []);

  return (
    <section
      ref={panelRef}
      className="extraction-results glass-card"
      id="extraction-results"
      aria-labelledby="extraction-title"
    >
      <div className="extraction-title">
        <h3 id="extraction-title">
          <CheckCircle size={18} color="var(--status-success)" /> Claim data extracted
        </h3>
        <div className="extraction-title-meta">
          <MockBadge source={result.source} />
          <span
            className="extraction-confidence"
            style={{ color: completenessColor(completeness) }}
            title="Share of the 11 claim fields found in the document"
          >
            {(completeness * 100).toFixed(0)}% complete
          </span>
          <button type="button" className="extraction-dismiss" onClick={onDismiss} aria-label="Close extraction results">
            <X size={16} />
          </button>
        </div>
      </div>

      <p className="extraction-subtitle">
        {document.filename}: {result.is_new_claim ? 'a new claim was created.' : 'the existing claim was updated.'}
      </p>

      <div className="extraction-fields">
        {FIELDS.map(({ label, key, format }) => {
          const value = data[key];
          const missing = value === null || value === undefined || value === '';
          return (
            <div key={key} className="extraction-field">
              <span className="extraction-field-label">{label}</span>
              <span className={`extraction-field-value ${missing ? 'extraction-field-value--missing' : ''}`}>
                {missing ? 'Not found' : format ? format(value) : String(value)}
              </span>
            </div>
          );
        })}
      </div>

      <div className="extraction-actions">
        {result.claim_id && (
          <Link to={`/claims/${result.claim_id}`} className="btn btn-secondary btn-sm">
            View claim
          </Link>
        )}
        {children}
      </div>
    </section>
  );
}
