import { useCallback, useEffect, useState } from 'react';

/**
 * Runs an async loader (usually an API call) and tracks its result.
 *
 * `load` must be referentially stable: define it at module level or wrap it in
 * useCallback. A new `load` identity starts a new query and discards the old data;
 * `refetch()` re-runs the current query and keeps the previous data visible until
 * the new response arrives. Pass `delay` (ms) to debounce, e.g. for search input.
 *
 * @returns {{ data: any, error: Error | null, loading: boolean,
 *   refetch: () => void, setData: (update: any) => void }}
 */
export function useApiQuery(load, { delay = 0 } = {}) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState({ load: null, version: -1, data: undefined, error: null });

  useEffect(() => {
    let active = true;
    const run = () => {
      Promise.resolve()
        .then(load)
        .then(
          (data) => {
            if (active) setResult({ load, version, data, error: null });
          },
          (error) => {
            if (active) setResult({ load, version, data: undefined, error });
          },
        );
    };

    if (delay > 0) {
      const timer = setTimeout(run, delay);
      return () => {
        active = false;
        clearTimeout(timer);
      };
    }
    run();
    return () => {
      active = false;
    };
  }, [load, version, delay]);

  const refetch = useCallback(() => setVersion((current) => current + 1), []);

  /** Updates the cached data locally, e.g. for optimistic updates. */
  const setData = useCallback((update) => {
    setResult((current) => ({
      ...current,
      data: typeof update === 'function' ? update(current.data) : update,
    }));
  }, []);

  const sameQuery = result.load === load;
  const settled = sameQuery && result.version === version;

  return {
    data: sameQuery ? result.data : undefined,
    error: settled ? result.error : null,
    loading: !settled,
    refetch,
    setData,
  };
}
