/**
 * Source tracing: finds where each extracted claim value appears in a
 * document's OCR text, so the interface can point at the exact line it came
 * from (or say plainly that it is not in the document).
 *
 * Matching is case-insensitive and treats any run of whitespace, including
 * line breaks, as one space. Amounts and dates are also matched in the common
 * ways documents print them ("$18,250.00", "06/15/2026", "Jun 15, 2026").
 */

/**
 * The eleven claim fields, ordered like the boxes of a claim form: pairs share
 * a row and `wide` fields take a whole row, so a two-column grid has no gaps.
 */
export const CLAIM_FIELDS = [
  { key: 'patient_name', label: 'Patient name', kind: 'text' },
  { key: 'policy_number', label: 'Policy number', kind: 'id' },
  { key: 'claim_number', label: 'Claim number', kind: 'id' },
  { key: 'provider_id', label: 'Provider ID', kind: 'id' },
  { key: 'diagnosis', label: 'Diagnosis', kind: 'text', wide: true },
  { key: 'date_of_service', label: 'Service date', kind: 'date' },
  { key: 'treatment_cost', label: 'Treatment cost', kind: 'currency' },
  { key: 'date_of_admission', label: 'Admission date', kind: 'date' },
  { key: 'date_of_discharge', label: 'Discharge date', kind: 'date' },
  { key: 'hospital_name', label: 'Hospital', kind: 'text', wide: true },
  { key: 'hospital_address', label: 'Hospital address', kind: 'text', wide: true },
];

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;

export function isBlank(value) {
  return value === null || value === undefined || String(value).trim() === '';
}

function collapseSpaces(value) {
  return String(value).replace(/\s+/g, ' ').trim();
}

function amountNeedles(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return [collapseSpaces(value)];
  const grouped = (digits) => amount.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const plain = (digits) => amount.toFixed(digits);
  const needles = [grouped(2), plain(2)];
  if (Number.isInteger(amount)) needles.push(grouped(0), plain(0));
  return needles;
}

function dateNeedles(value) {
  const text = collapseSpaces(value);
  const match = ISO_DATE.exec(text);
  if (!match) return [text];
  const [, year, month, day] = match;
  const m = Number(month);
  const d = Number(day);
  const name = MONTHS[m - 1];
  if (!name) return [text];
  return [
    `${year}-${month}-${day}`,
    `${year}/${month}/${day}`,
    `${month}/${day}/${year}`,
    `${m}/${d}/${year}`,
    `${month}-${day}-${year}`,
    `${name} ${d}, ${year}`,
    `${name.slice(0, 3)} ${d}, ${year}`,
    `${d} ${name} ${year}`,
    `${d} ${name.slice(0, 3)} ${year}`,
  ];
}

/** The strings to look for in a document for one field value, most specific first. */
export function needlesFor(kind, value) {
  if (isBlank(value)) return [];
  let needles;
  if (kind === 'currency') needles = amountNeedles(value);
  else if (kind === 'date') needles = dateNeedles(value);
  else needles = [collapseSpaces(value)];
  return [...new Set(needles.filter((needle) => needle.length >= 2))];
}

/** Lower-cased text with whitespace runs collapsed, plus a map back to original offsets. */
function normalise(text) {
  let norm = '';
  const map = [];
  let inSpace = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      if (!inSpace) {
        norm += ' ';
        map.push(i);
        inSpace = true;
      }
    } else {
      norm += ch.toLowerCase();
      map.push(i);
      inSpace = false;
    }
  }
  return { norm, map };
}

const isAlnum = (ch) => ch !== undefined && /[\p{L}\p{N}]/u.test(ch);
const isDigit = (ch) => ch !== undefined && /\d/.test(ch);

/** True when [start, end) of `text` is a whole value, not part of a longer word or number. */
function atBoundary(text, start, end, numeric) {
  const before = text[start - 1];
  const after = text[end];
  if (isAlnum(before) && isAlnum(text[start])) return false;
  if (isAlnum(after) && isAlnum(text[end - 1])) return false;
  if (numeric) {
    // "12,000" must not match inside "112,000" or "12,000.50".
    if (/[.,]/.test(before ?? '') && isDigit(text[start - 2])) return false;
    if (/[.,]/.test(after ?? '') && isDigit(text[end + 1])) return false;
  }
  return true;
}

/** Character offsets where each line of `text` starts. */
function lineStarts(text) {
  const starts = [0];
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '\n') starts.push(i + 1);
  }
  return starts;
}

/** 1-based line number of a character offset. */
function lineOf(starts, offset) {
  let low = 0;
  let high = starts.length - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if (starts[mid] <= offset) low = mid;
    else high = mid - 1;
  }
  return low + 1;
}

/**
 * Traces field values to the document text.
 *
 * @param {string} text OCR text of the source document.
 * @param {{ key: string, kind: string, value: unknown }[]} fields
 * @returns {{
 *   marks: { start: number, end: number, keys: string[] }[],
 *   fields: Record<string, { status: 'found' | 'not-found' | 'missing', lines: number[] }>,
 * }} `marks` are non-overlapping ranges of `text`, sorted by position.
 */
export function traceFields(text, fields) {
  const source = typeof text === 'string' ? text : '';
  const { norm, map } = normalise(source);
  const starts = lineStarts(source);
  const candidates = [];
  const result = {};

  for (const field of fields) {
    const needles = needlesFor(field.kind, field.value);
    if (needles.length === 0) {
      result[field.key] = { status: 'missing', lines: [] };
      continue;
    }
    const numeric = field.kind === 'currency';
    const seen = new Set();
    for (const needle of needles) {
      const query = collapseSpaces(needle).toLowerCase();
      let from = 0;
      while (query && from <= norm.length) {
        const index = norm.indexOf(query, from);
        if (index === -1) break;
        from = index + 1;
        let start = map[index];
        const end = map[index + query.length - 1] + 1;
        if (!atBoundary(source, start, end, numeric)) continue;
        // Take the currency sign with the amount when the document prints one.
        if (numeric && source[start - 1] === '$') start -= 1;
        const id = `${start}:${end}`;
        if (seen.has(id)) continue;
        seen.add(id);
        candidates.push({ start, end, key: field.key });
      }
    }
    result[field.key] = { status: 'not-found', lines: [] };
  }

  // Longest match first, so a value never loses its mark to a shorter one inside it.
  candidates.sort((a, b) => (b.end - b.start) - (a.end - a.start) || a.start - b.start);
  const marks = [];
  for (const candidate of candidates) {
    const covering = marks.find((mark) => mark.start <= candidate.start && candidate.end <= mark.end);
    if (covering) {
      if (!covering.keys.includes(candidate.key)) covering.keys.push(candidate.key);
    } else if (!marks.some((mark) => candidate.start < mark.end && mark.start < candidate.end)) {
      marks.push({ start: candidate.start, end: candidate.end, keys: [candidate.key] });
    } else {
      continue;
    }
    const entry = result[candidate.key];
    entry.status = 'found';
    for (let line = lineOf(starts, candidate.start); line <= lineOf(starts, candidate.end - 1); line += 1) {
      if (!entry.lines.includes(line)) entry.lines.push(line);
    }
  }

  marks.sort((a, b) => a.start - b.start);
  for (const entry of Object.values(result)) entry.lines.sort((a, b) => a - b);
  return { marks, fields: result };
}

/**
 * Splits text into numbered lines, each with the marks that fall on it as
 * segments: `{ number, segments: [{ text, keys? }] }`.
 */
export function layoutLines(text, marks = []) {
  const source = typeof text === 'string' ? text : '';
  const lines = [];
  let offset = 0;
  let markIndex = 0;
  for (const [index, lineText] of source.split('\n').entries()) {
    const lineStart = offset;
    const lineEnd = offset + lineText.length;
    const segments = [];
    let cursor = lineStart;
    while (markIndex < marks.length && marks[markIndex].end <= lineStart) markIndex += 1;
    for (let i = markIndex; i < marks.length && marks[i].start < lineEnd; i += 1) {
      const start = Math.max(marks[i].start, lineStart);
      const end = Math.min(marks[i].end, lineEnd);
      if (end <= start) continue;
      if (start > cursor) segments.push({ text: source.slice(cursor, start) });
      segments.push({ text: source.slice(start, end), keys: marks[i].keys });
      cursor = end;
    }
    if (cursor < lineEnd) segments.push({ text: source.slice(cursor, lineEnd) });
    lines.push({ number: index + 1, segments });
    offset = lineEnd + 1;
  }
  return lines;
}

const listFormat = new Intl.ListFormat('en-US', { style: 'long', type: 'conjunction' });

/** "Line 4", "Lines 4 and 8", "Not in this document" or "Missing". */
export function describeTrace(trace) {
  if (!trace || trace.status === 'missing') return 'Missing';
  if (trace.status === 'not-found' || trace.lines.length === 0) return 'Not in this document';
  if (trace.lines.length === 1) return `Line ${trace.lines[0]}`;
  return `Lines ${listFormat.format(trace.lines.map(String))}`;
}
