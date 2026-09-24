import { useCallback, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import ClaimDetail from '../components/Claims/ClaimDetail';
import { ErrorState, LoadingState } from '../components/Shared/StateMessage';
import { useApiQuery } from '../hooks/useApiQuery';
import { claimsApi, getErrorMessage } from '../services/api';
import '../components/Claims/ClaimDetail.css';

export default function ClaimDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const loadClaim = useCallback(() => claimsApi.get(id), [id]);
  const claim = useApiQuery(loadClaim);
  const [statusUpdate, setStatusUpdate] = useState({ pending: null, error: null });

  const handleUpdateStatus = async (status) => {
    setStatusUpdate({ pending: status, error: null });
    try {
      const updated = await claimsApi.update(id, { status });
      claim.setData(updated);
      setStatusUpdate({ pending: null, error: null });
    } catch (err) {
      setStatusUpdate({
        pending: null,
        error: getErrorMessage(err, { 401: 'Changing a claim status is disabled on the public demo.' }),
      });
    }
  };

  let content;
  if (claim.error) {
    content = claim.error.status === 404
      ? <ErrorState title="Claim not found" message="It may have been deleted, or the link is incorrect." />
      : <ErrorState title="Couldn't load this claim" message={getErrorMessage(claim.error)} onRetry={claim.refetch} />;
  } else if (!claim.data) {
    content = <LoadingState label="Loading claim…" />;
  } else {
    content = (
      <ClaimDetail
        claim={claim.data}
        pendingStatus={statusUpdate.pending}
        statusError={statusUpdate.error}
        onUpdateStatus={handleUpdateStatus}
        onDismissStatusError={() => setStatusUpdate({ pending: null, error: null })}
      />
    );
  }

  return (
    <div className="page-enter" id="claim-detail-page">
      <button className="claim-detail-back" onClick={() => navigate('/claims')} id="back-to-claims">
        <ArrowLeft size={18} /> Back to Claims
      </button>
      {content}
    </div>
  );
}
