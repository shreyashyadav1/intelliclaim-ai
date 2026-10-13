import { describe, expect, it } from 'vitest';
import { formatCurrency, formatDate, formatFileSize, formatScore, riskColor, riskLevel } from './format';

describe('formatDate', () => {
  it('shows date-only values as the same calendar day in every time zone', () => {
    expect(formatDate('2026-06-01', { month: 'short', day: 'numeric' })).toBe('Jun 1');
  });

  it('returns a placeholder for missing or invalid dates', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate('not a date')).toBe('—');
  });
});

describe('formatCurrency', () => {
  it('shows cents only when present', () => {
    expect(formatCurrency(87500)).toBe('$87,500');
    expect(formatCurrency(107364.1)).toBe('$107,364.10');
  });

  it('returns a placeholder instead of "$undefined"', () => {
    expect(formatCurrency(undefined)).toBe('—');
    expect(formatCurrency(null)).toBe('—');
  });
});

describe('risk helpers', () => {
  it('uses the backend thresholds', () => {
    expect(riskLevel(59.9)).toBe('medium');
    expect(riskLevel(60)).toBe('high');
    expect(riskLevel(0)).toBe('low');
    expect(riskColor(85)).toBe('#ef4444');
  });

  it('rounds scores to one decimal place', () => {
    expect(formatScore(72.46)).toBe('72.5');
    expect(formatScore(undefined)).toBe('—');
  });
});

describe('formatFileSize', () => {
  it('picks a readable unit', () => {
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(2048)).toBe('2.0 KB');
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB');
  });
});
