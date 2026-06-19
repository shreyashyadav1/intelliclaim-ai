import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import ClaimDetail from '../components/Claims/ClaimDetail';
import { claimsApi } from '../services/api';

export default function ClaimDetailPage() {
  const { id } = useParams();
  const [claim, setClaim] = useState(null);

  useEffect(() => {
    const fetchClaim = async () => {
      try {
        const result = await claimsApi.get(id);
        setClaim(result);
      } catch {
        // Demo data used by ClaimDetail
      }
    };
    if (id) fetchClaim();
  }, [id]);

  const handleUpdateStatus = async (claimId, newStatus) => {
    try {
      const updated = await claimsApi.update(claimId, { status: newStatus });
      setClaim(updated);
    } catch {
      setClaim(prev => prev ? { ...prev, status: newStatus } : prev);
    }
  };

  return (
    <div className="page-enter" id="claim-detail-page">
      <ClaimDetail claim={claim} onUpdateStatus={handleUpdateStatus} />
    </div>
  );
}
