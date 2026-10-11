import { useSyncExternalStore } from 'react';
import api from '../services/api';

// The public demo backend can be offline for extended periods; check often
// enough to notice recovery without hammering the server.
export const HEALTH_CHECK_INTERVAL = 60_000;
const HEALTH_CHECK_TIMEOUT = 5_000;

/** Before the first check answers, the API is assumed reachable and real. */
const UNKNOWN = Object.freeze({ offline: false, mockLlm: false });

let snapshot = UNKNOWN;
let timer = null;
let generation = 0;
const listeners = new Set();

function publish(next) {
  if (next.offline === snapshot.offline && next.mockLlm === snapshot.mockLlm) return;
  snapshot = next;
  listeners.forEach((listener) => listener());
}

async function check(run) {
  try {
    const health = await api.get('/health', { timeout: HEALTH_CHECK_TIMEOUT });
    if (run === generation) publish({ offline: false, mockLlm: health?.mock_llm === true });
  } catch {
    if (run === generation) publish({ ...snapshot, offline: true });
  }
}

// One poll is shared by every component that reads the API's health; it
// starts with the first subscriber and stops (and forgets) with the last.
function subscribe(listener) {
  listeners.add(listener);
  if (listeners.size === 1) {
    generation += 1;
    const run = generation;
    check(run);
    timer = setInterval(() => check(run), HEALTH_CHECK_INTERVAL);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      clearInterval(timer);
      timer = null;
      generation += 1;
      snapshot = UNKNOWN;
    }
  };
}

const getSnapshot = () => snapshot;
const getServerSnapshot = () => UNKNOWN;

/**
 * Polls GET /health (relative to the API base URL) while any component uses it.
 *
 * Any failure — a network error, a timeout, or an HTTP error status such as a
 * 503 (the backend uses this to report the database being down) — counts as
 * offline. `mockLlm` is true when the backend reports MOCK_LLM, i.e. its AI
 * output comes from the labelled mock model.
 *
 * @returns {{ offline: boolean, mockLlm: boolean }}
 */
export function useApiHealth() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
