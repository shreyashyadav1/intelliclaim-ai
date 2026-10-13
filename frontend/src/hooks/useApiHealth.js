import { useEffect, useState } from 'react';
import api from '../services/api';

// The public demo backend can be offline for extended periods; check often
// enough to notice recovery without hammering the server.
export const HEALTH_CHECK_INTERVAL = 60_000;
const HEALTH_CHECK_TIMEOUT = 5_000;

/**
 * Polls GET /health (relative to the API base URL) on mount and every
 * HEALTH_CHECK_INTERVAL after that.
 *
 * Any failure — a network error, a timeout, or an HTTP error status such as a
 * 503 (the backend uses this to report the database being down) — counts as
 * offline. Returns `true` while the API is believed to be unreachable.
 */
export function useApiHealth() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        await api.get('/health', { timeout: HEALTH_CHECK_TIMEOUT });
        if (!cancelled) setOffline(false);
      } catch {
        if (!cancelled) setOffline(true);
      }
    };

    check();
    const timer = setInterval(check, HEALTH_CHECK_INTERVAL);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return offline;
}
