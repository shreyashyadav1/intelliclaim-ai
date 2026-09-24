import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import ClaimsList from '../components/Claims/ClaimsList';
import { useApiQuery } from '../hooks/useApiQuery';
import { claimsApi } from '../services/api';

// GET /claims caps `limit` at 100.
const PAGE_SIZE = 100;
const SEARCH_DEBOUNCE_MS = 300;

export default function ClaimsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get('search') ?? '';
  const status = searchParams.get('status') ?? 'all';
  const term = search.trim();

  const loadClaims = useCallback(
    () => claimsApi.list({
      limit: PAGE_SIZE,
      search: term || undefined,
      status: status === 'all' ? undefined : status,
    }),
    [term, status],
  );
  const claims = useApiQuery(loadClaims, {
    delay: term ? SEARCH_DEBOUNCE_MS : 0,
    keepPreviousData: true,
  });

  // Filters live in the URL so the header search and browser history can drive them.
  const setParam = (key, value, defaultValue) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (value && value !== defaultValue) next.set(key, value);
      else next.delete(key);
      return next;
    }, { replace: true });
  };

  return (
    <div className="page-enter" id="claims-page">
      <ClaimsList
        claims={claims.data?.claims}
        total={claims.data?.total}
        loading={claims.loading}
        error={claims.error}
        onRetry={claims.refetch}
        search={search}
        onSearchChange={(value) => setParam('search', value, '')}
        status={status}
        onStatusChange={(value) => setParam('status', value, 'all')}
      />
    </div>
  );
}
