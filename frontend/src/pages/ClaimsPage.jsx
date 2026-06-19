import { useState, useEffect } from 'react';
import ClaimsList from '../components/Claims/ClaimsList';
import { claimsApi } from '../services/api';

export default function ClaimsPage() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    const fetchClaims = async () => {
      try {
        const result = await claimsApi.list({ limit: 50 });
        setClaims(result.claims || []);
      } catch {
        // Demo data used by ClaimsList
      }
    };
    fetchClaims();
  }, []);

  return (
    <div className="page-enter" id="claims-page">
      <ClaimsList claims={claims} />
    </div>
  );
}
