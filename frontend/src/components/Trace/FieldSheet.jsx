import { useId } from 'react';
import { formatCurrency, formatDate } from '../../utils/format';
import { describeTrace, isBlank } from '../../utils/trace';
import './Trace.css';

function display(field) {
  if (field.kind === 'currency') return formatCurrency(field.value);
  if (field.kind === 'date') return formatDate(field.value);
  return String(field.value);
}

function TraceReference({ field, trace, onActivate, onLocate }) {
  const text = describeTrace(trace);
  if (trace.status !== 'found') {
    return (
      <span className="trace-ref trace-ref--absent">
        <span className="trace-swatch trace-swatch--absent" aria-hidden="true" />
        {text}
      </span>
    );
  }
  return (
    <button
      type="button"
      className="trace-ref"
      onClick={() => onLocate(field.key)}
      onFocus={() => onActivate(field.key)}
      onBlur={() => onActivate(null)}
      aria-label={`Show ${field.label.toLowerCase()} in the document: ${text}`}
    >
      <span className="trace-swatch" aria-hidden="true" />
      {text}
    </button>
  );
}

/**
 * Claim fields laid out like the boxes of a claim form. With a trace, every
 * value says where it came from: a line reference that finds it in the
 * source document, "Not in this document", or "Missing".
 */
export default function FieldSheet({
  title = 'Extracted fields',
  headingLevel = 2,
  fields,
  trace,
  completeness,
  activeKey,
  onActivate,
  onLocate,
  children,
}) {
  const headingId = useId();
  const Heading = `h${headingLevel}`;
  const present = fields.filter((field) => !isBlank(field.value));
  const traced = trace ? present.filter((field) => trace.fields[field.key]?.status === 'found').length : 0;
  const hasCompleteness = typeof completeness === 'number' && Number.isFinite(completeness);
  const percent = hasCompleteness ? Math.round(Math.min(Math.max(completeness, 0), 1) * 100) : null;

  return (
    <section className="field-sheet" aria-labelledby={headingId}>
      <div className="field-sheet-head">
        <Heading id={headingId} className="field-sheet-title">{title}</Heading>
        <p className="field-sheet-summary">
          {trace
            ? `${traced} of ${present.length} values found in this document.`
            : `${present.length} of ${fields.length} fields have a value.`}
        </p>
      </div>

      {hasCompleteness && (
        <div className="field-sheet-completeness">
          <span className="field-sheet-completeness-label" title="Share of the 11 claim fields found by extraction">
            Completeness
          </span>
          <span className="meter" aria-hidden="true">
            <span className="meter-fill" style={{ transform: `scaleX(${percent / 100})` }} />
          </span>
          <span className="field-sheet-completeness-value tabular">{`${percent}%`}</span>
        </div>
      )}

      <dl className="field-grid">
        {fields.map((field) => {
          const missing = isBlank(field.value);
          const fieldTrace = trace?.fields[field.key];
          const traceable = fieldTrace?.status === 'found';
          return (
            <div
              key={field.key}
              className="field-cell"
              data-wide={field.wide || undefined}
              data-active={(traceable && activeKey === field.key) || undefined}
              onPointerEnter={traceable ? () => onActivate(field.key) : undefined}
              onPointerLeave={traceable ? () => onActivate(null) : undefined}
            >
              <dt className="field-label">{field.label}</dt>
              <dd
                className={`field-value${missing ? ' field-value--missing' : ''}${field.kind === 'text' ? '' : ' tabular'}`}
                translate={field.kind === 'id' ? 'no' : undefined}
              >
                {missing ? 'Missing' : display(field)}
              </dd>
              {fieldTrace && !missing && (
                <dd className="field-trace">
                  <TraceReference field={field} trace={fieldTrace} onActivate={onActivate} onLocate={onLocate} />
                </dd>
              )}
            </div>
          );
        })}
      </dl>
      {children}
    </section>
  );
}
