import { memo, useMemo } from 'react';
import { layoutLines } from '../../utils/trace';

/**
 * A document's text as numbered lines, with traced values marked. Marks whose
 * field is active switch to the pressed highlighter; hovering a mark makes its
 * field active.
 */
function SourceLines({ text, marks, activeKey, activeLines, labels = {}, onHover }) {
  const lines = useMemo(() => layoutLines(text, marks), [text, marks]);

  return (
    <ol className="source-lines" role="list">
      {lines.map((line) => (
        <li
          key={line.number}
          className="source-line"
          data-line={line.number}
          data-active={activeLines?.includes(line.number) || undefined}
        >
          <span className="source-line-number" aria-hidden="true">{line.number}</span>
          <span className="source-line-text">
            {line.segments.length === 0
              ? ' '
              : line.segments.map((segment, index) => (segment.keys ? (
                <mark
                  key={index}
                  className="trace-mark"
                  data-active={segment.keys.includes(activeKey) || undefined}
                  title={segment.keys.map((key) => labels[key] ?? key).join(', ')}
                  onPointerEnter={onHover ? () => onHover(segment.keys[0]) : undefined}
                  onPointerLeave={onHover ? () => onHover(null) : undefined}
                >
                  {segment.text}
                </mark>
              ) : segment.text))}
          </span>
        </li>
      ))}
    </ol>
  );
}

export default memo(SourceLines);
