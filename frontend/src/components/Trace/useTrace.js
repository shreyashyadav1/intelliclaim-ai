import { useCallback, useMemo, useRef, useState } from 'react';
import { traceFields } from '../../utils/trace';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/**
 * Shared state for a source document and the fields traced into it: which
 * field is active (hovered or focused), and `locate(key)`, which scrolls the
 * document to the first line the value was found on and flashes it.
 *
 * `text` is null when no document text is available; every field then has
 * no trace rather than a "not in this document" result.
 */
export function useTrace(text, fields) {
  const [activeKey, setActiveKey] = useState(null);
  const sheetRef = useRef(null);

  const trace = useMemo(
    () => (typeof text === 'string' ? traceFields(text, fields) : null),
    [text, fields],
  );

  const locate = useCallback((key) => {
    setActiveKey(key);
    const line = trace?.fields[key]?.lines[0];
    const container = sheetRef.current;
    const target = line && container?.querySelector(`[data-line="${line}"]`);
    if (!target) return;

    const behavior = prefersReducedMotion() ? 'auto' : 'smooth';
    if (container.scrollHeight > container.clientHeight) {
      const top = target.offsetTop - container.clientHeight / 2 + target.offsetHeight / 2;
      container.scrollTo({ top: Math.max(top, 0), behavior });
    }
    const box = target.getBoundingClientRect();
    if (box.top < 0 || box.bottom > window.innerHeight) {
      target.scrollIntoView({ block: 'center', behavior });
    }
    if (!prefersReducedMotion() && typeof target.animate === 'function') {
      try {
        target.animate([{ opacity: 1 }, { opacity: 0 }], {
          duration: 520,
          easing: 'cubic-bezier(0.23, 1, 0.32, 1)',
          pseudoElement: '::after',
        });
      } catch {
        // Pseudo-element animation is unsupported; the active highlight still shows the line.
      }
    }
  }, [trace]);

  return { trace, activeKey, setActiveKey, locate, sheetRef };
}
