import './ExtractionResults.css';

export default function ExtractionResults({ result }) {
  if (!result) return null;

  const fields = [
    { label: 'Policy Number', key: 'policy_number' },
    { label: 'Claim Number', key: 'claim_number' },
    { label: 'Patient Name', key: 'patient_name' },
    { label: 'Diagnosis', key: 'diagnosis' },
    { label: 'Treatment Cost', key: 'treatment_cost', format: (v) => `$${Number(v).toLocaleString()}` },
    { label: 'Hospital Name', key: 'hospital_name' },
    { label: 'Hospital Address', key: 'hospital_address' },
    { label: 'Provider ID', key: 'provider_id' },
    { label: 'Service Date', key: 'date_of_service' },
    { label: 'Admission Date', key: 'date_of_admission' },
    { label: 'Discharge Date', key: 'date_of_discharge' },
  ];

  const data = result.extracted_data || result;
  const confidence = result.confidence_score || 0;

  return (
    <div className="extraction-results glass-card" id="extraction-results">
      <h3 className="extraction-title">
        AI Extraction Results
        <span className="extraction-confidence" style={{ color: confidence > 0.8 ? '#10b981' : confidence > 0.5 ? '#f59e0b' : '#ef4444' }}>
          {(confidence * 100).toFixed(0)}% confidence
        </span>
      </h3>
      <div className="extraction-fields">
        {fields.map(({ label, key, format }) => {
          const value = data[key];
          if (value === null || value === undefined) return null;
          return (
            <div key={key} className="extraction-field">
              <span className="extraction-field-label">{label}</span>
              <span className="extraction-field-value">
                {format ? format(value) : String(value)}
              </span>
              <div className="extraction-field-bar">
                <div className="extraction-field-bar-fill" style={{ width: `${Math.random() * 20 + 80}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
