import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, ChevronDown } from 'lucide-react';
import Badge from '../Shared/Badge';
import './ClaimsList.css';

const demoClaims = [
  { id: 'clm-1', claim_number: 'CLM-2026-10001', policy_number: 'POL-2026-50001', patient_name: 'Sarah Johnson', diagnosis: 'ACL Tear (S83.5)', treatment_cost: 34500, hospital_name: 'Metro General Hospital', status: 'approved', risk_score: 15, created_at: '2026-06-15' },
  { id: 'clm-2', claim_number: 'CLM-2026-10002', policy_number: 'POL-2026-50002', patient_name: 'Michael Chen', diagnosis: 'Type 2 Diabetes (E11.9)', treatment_cost: 12800, hospital_name: 'City Medical Center', status: 'pending', risk_score: 22, created_at: '2026-06-14' },
  { id: 'clm-3', claim_number: 'CLM-2026-10003', policy_number: 'POL-2026-50003', patient_name: 'Emily Rodriguez', diagnosis: 'Acute Appendicitis (K35.80)', treatment_cost: 28900, hospital_name: "St. Mary's Hospital", status: 'approved', risk_score: 8, created_at: '2026-06-13' },
  { id: 'clm-4', claim_number: 'CLM-2026-10004', policy_number: 'POL-2026-50004', patient_name: 'James Williams', diagnosis: 'Lumbar Disc Herniation (M51.16)', treatment_cost: 67200, hospital_name: 'Spine Care Institute', status: 'flagged', risk_score: 72, created_at: '2026-06-12' },
  { id: 'clm-5', claim_number: 'CLM-2026-10005', policy_number: 'POL-2026-50005', patient_name: 'Amanda Thompson', diagnosis: 'Knee Replacement (Z96.651)', treatment_cost: 89500, hospital_name: 'Orthopedic Surgical Center', status: 'pending', risk_score: 45, created_at: '2026-06-11' },
  { id: 'clm-6', claim_number: 'CLM-2026-10006', policy_number: 'POL-2026-50006', patient_name: 'Robert Davis', diagnosis: 'Coronary Artery Disease (I25.10)', treatment_cost: 156000, hospital_name: 'Heart & Vascular Center', status: 'flagged', risk_score: 85, created_at: '2026-06-10' },
  { id: 'clm-7', claim_number: 'CLM-2026-10007', policy_number: 'POL-2026-50007', patient_name: 'Lisa Garcia', diagnosis: 'Cholecystitis (K81.0)', treatment_cost: 19200, hospital_name: 'Regional Medical Center', status: 'approved', risk_score: 5, created_at: '2026-06-09' },
  { id: 'clm-8', claim_number: 'CLM-2026-10008', policy_number: 'POL-2026-50008', patient_name: 'David Brown', diagnosis: 'Rotator Cuff Tear (M75.10)', treatment_cost: 31400, hospital_name: 'Sports Medicine Clinic', status: 'approved', risk_score: 18, created_at: '2026-06-08' },
  { id: 'clm-9', claim_number: 'CLM-2026-10009', policy_number: 'POL-2026-50009', patient_name: 'Jennifer Martinez', diagnosis: 'Breast Cancer Stage II (C50.9)', treatment_cost: 124500, hospital_name: 'Cancer Treatment Center', status: 'approved', risk_score: 12, created_at: '2026-06-07' },
  { id: 'clm-10', claim_number: 'CLM-2026-10010', policy_number: 'POL-2026-50010', patient_name: 'Christopher Lee', diagnosis: 'Pneumonia (J18.9)', treatment_cost: 8900, hospital_name: 'Community Hospital', status: 'rejected', risk_score: 55, created_at: '2026-06-06' },
];

const statuses = ['all', 'pending', 'approved', 'rejected', 'flagged'];

function getRiskColor(score) {
  if (score >= 60) return '#ef4444';
  if (score >= 30) return '#f59e0b';
  return '#10b981';
}

export default function ClaimsList({ claims }) {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const data = claims && claims.length > 0 ? claims : demoClaims;

  const filtered = data.filter(claim => {
    const matchesSearch = !search || 
      claim.claim_number?.toLowerCase().includes(search.toLowerCase()) ||
      claim.patient_name?.toLowerCase().includes(search.toLowerCase()) ||
      claim.diagnosis?.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || claim.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="claims-list" id="claims-list">
      <div className="claims-list-toolbar">
        <div className="claims-search-wrapper">
          <Search size={16} className="claims-search-icon" />
          <input
            type="text"
            placeholder="Search claims..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="claims-search-input"
            id="claims-search-input"
          />
        </div>
        <div className="claims-filter-tabs">
          {statuses.map((s) => (
            <button
              key={s}
              className={`claims-filter-tab ${statusFilter === s ? 'active' : ''}`}
              onClick={() => setStatusFilter(s)}
              id={`filter-${s}`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="claims-table-wrapper glass-card">
        <table className="claims-table">
          <thead>
            <tr>
              <th>Claim #</th>
              <th>Policy #</th>
              <th>Patient</th>
              <th>Diagnosis</th>
              <th>Cost</th>
              <th>Status</th>
              <th>Risk</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((claim) => (
              <tr
                key={claim.id}
                className="claims-table-row"
                onClick={() => navigate(`/claims/${claim.id}`)}
              >
                <td className="mono-cell accent">{claim.claim_number}</td>
                <td className="mono-cell">{claim.policy_number}</td>
                <td>{claim.patient_name}</td>
                <td className="diagnosis-cell">{claim.diagnosis}</td>
                <td className="mono-cell bold">${claim.treatment_cost?.toLocaleString()}</td>
                <td><Badge variant={claim.status}>{claim.status}</Badge></td>
                <td>
                  <span className="risk-pill" style={{ color: getRiskColor(claim.risk_score), background: `${getRiskColor(claim.risk_score)}15` }}>
                    {claim.risk_score}
                  </span>
                </td>
                <td className="date-cell">{new Date(claim.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan="8" className="claims-empty">No claims found matching your criteria</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
