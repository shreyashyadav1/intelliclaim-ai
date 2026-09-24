const PLACEHOLDER = '—';
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const HAS_TIME_ZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

function isBlank(value) {
  return value === null || value === undefined || value === '';
}

/** Formats a USD amount, showing cents only when there are any. */
export function formatCurrency(value) {
  const amount = Number(value);
  if (isBlank(value) || !Number.isFinite(amount)) return PLACEHOLDER;
  return amount.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Formats an API date. Date-only values ("2026-06-15") are calendar dates and are
 * shown as-is in every time zone; timestamps without an offset are stored as UTC.
 */
export function formatDate(value, options = { month: 'short', day: 'numeric', year: 'numeric' }) {
  if (isBlank(value)) return PLACEHOLDER;
  const text = String(value);
  let date;
  let timeZone;
  if (DATE_ONLY.test(text)) {
    date = new Date(`${text}T00:00:00Z`);
    timeZone = 'UTC';
  } else {
    date = new Date(text.includes('T') && !HAS_TIME_ZONE.test(text) ? `${text}Z` : text);
  }
  if (Number.isNaN(date.getTime())) return PLACEHOLDER;
  return date.toLocaleDateString('en-US', { ...options, timeZone });
}

export function formatFileSize(bytes) {
  const size = Number(bytes);
  if (isBlank(bytes) || !Number.isFinite(size) || size < 0) return PLACEHOLDER;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** "medical_report" -> "medical report" */
export function humanize(value) {
  return isBlank(value) ? '' : String(value).replace(/_/g, ' ');
}

/** Risk score (0-100) rounded to one decimal place. */
export function formatScore(score) {
  const value = Number(score);
  if (isBlank(score) || !Number.isFinite(value)) return PLACEHOLDER;
  return String(Math.round(value * 10) / 10);
}

/** Risk bands used by the backend validator: >= 60 high, >= 30 medium, otherwise low. */
export function riskLevel(score) {
  const value = Number(score) || 0;
  if (value >= 60) return 'high';
  if (value >= 30) return 'medium';
  return 'low';
}

const RISK_COLORS = { high: '#ef4444', medium: '#f59e0b', low: '#10b981' };

/** Hex color for a risk score; callers append an alpha suffix for tinted backgrounds. */
export function riskColor(score) {
  return RISK_COLORS[riskLevel(score)];
}
