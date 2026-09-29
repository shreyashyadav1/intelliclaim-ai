import { useState } from 'react';
import { useApiHealth } from '../../hooks/useApiHealth';
import Notice from './Notice';

const REPO_URL = 'https://github.com/shreyashyadav1/intelliclaim-ai';

/**
 * Site-wide notice shown while the public demo's backend is unreachable.
 * Pages keep their own error states for individual failed requests; this
 * banner only speaks to the "the whole API is down" case.
 */
export default function OfflineBanner() {
  const offline = useApiHealth();
  const [dismissed, setDismissed] = useState(false);
  // Tracks whether `dismissed` still applies to the current outage. Updating
  // state during render (rather than in an effect) is the recommended way to
  // reset it the moment a new outage starts: https://react.dev/learn/you-might-not-need-an-effect
  const [wasOffline, setWasOffline] = useState(offline);
  if (offline !== wasOffline) {
    setWasOffline(offline);
    if (offline) setDismissed(false);
  }

  if (!offline || dismissed) return null;

  return (
    <div className="offline-banner">
      <Notice tone="info" onDismiss={() => setDismissed(true)}>
        The live demo&rsquo;s server is offline right now, so data can&rsquo;t load. The
        source code, tests and screenshots are on{' '}
        <a href={REPO_URL} target="_blank" rel="noreferrer">GitHub</a>.
      </Notice>
    </div>
  );
}
