import { describe, expect, it } from 'vitest';
import { describeTrace, layoutLines, needlesFor, traceFields } from './trace';

const REPORT = [
  'Patient: Sarah Johnson',
  'Policy: POL-2026-50001',
  'Diagnosis: ACL Tear (S83.5)',
  'Hospital: Metro General Hospital',
  'Treatment Cost: $33,123.45',
  'Date of Service: 2026-09-01',
  '',
  'Clinical Notes: Treatment was administered at Metro General',
  'Hospital. Total charges amount to $33,123.45.',
].join('\n');

const field = (key, kind, value) => ({ key, kind, value });

describe('traceFields', () => {
  it('finds each value and the lines it is on', () => {
    const { fields } = traceFields(REPORT, [
      field('patient_name', 'text', 'Sarah Johnson'),
      field('policy_number', 'id', 'POL-2026-50001'),
      field('diagnosis', 'text', 'ACL Tear (S83.5)'),
      field('date_of_service', 'date', '2026-09-01'),
    ]);

    expect(fields.patient_name).toEqual({ status: 'found', lines: [1] });
    expect(fields.policy_number).toEqual({ status: 'found', lines: [2] });
    expect(fields.diagnosis).toEqual({ status: 'found', lines: [3] });
    expect(fields.date_of_service).toEqual({ status: 'found', lines: [6] });
  });

  it('matches across line breaks and differences in case', () => {
    const { fields } = traceFields(REPORT, [field('hospital_name', 'text', 'metro general hospital')]);

    // Line 4, and again where the clinical notes wrap the name onto line 9.
    expect(fields.hospital_name.lines).toEqual([4, 8, 9]);
  });

  it('matches amounts as printed, including the currency sign', () => {
    const { marks, fields } = traceFields(REPORT, [field('treatment_cost', 'currency', 33123.45)]);

    expect(fields.treatment_cost.lines).toEqual([5, 9]);
    expect(marks.map((mark) => REPORT.slice(mark.start, mark.end))).toEqual(['$33,123.45', '$33,123.45']);
  });

  it('does not match a number inside a longer number', () => {
    const { fields } = traceFields('Total: $112,000.50', [field('treatment_cost', 'currency', 12000)]);

    expect(fields.treatment_cost.status).toBe('not-found');
  });

  it('does not match a name inside a longer word', () => {
    const { fields } = traceFields('Referred by Dr. Kleeman', [field('patient_name', 'text', 'Lee')]);

    expect(fields.patient_name.status).toBe('not-found');
  });

  it('matches dates written out or in US order', () => {
    const { fields } = traceFields('Admitted Sep 1, 2026; discharged 09/04/2026.', [
      field('date_of_admission', 'date', '2026-09-01'),
      field('date_of_discharge', 'date', '2026-09-04'),
    ]);

    expect(fields.date_of_admission.status).toBe('found');
    expect(fields.date_of_discharge.status).toBe('found');
  });

  it('reports values that are missing or absent from the text', () => {
    const { fields } = traceFields(REPORT, [
      field('claim_number', 'id', null),
      field('provider_id', 'id', 'NPI-1234567890'),
    ]);

    expect(fields.claim_number.status).toBe('missing');
    expect(fields.provider_id).toEqual({ status: 'not-found', lines: [] });
  });

  it('shares one mark between fields with the same value and never overlaps marks', () => {
    const { marks } = traceFields('Billed by Lakeside Clinic, Lakeside', [
      field('hospital_name', 'text', 'Lakeside Clinic'),
      field('hospital_address', 'text', 'Lakeside'),
    ]);

    expect(marks).toEqual([
      { start: 10, end: 25, keys: ['hospital_name', 'hospital_address'] },
      { start: 27, end: 35, keys: ['hospital_address'] },
    ]);
  });
});

describe('layoutLines', () => {
  it('numbers every line and splits marked text into segments', () => {
    const text = 'Patient: Dana\n\nTotal: $10';
    const { marks } = traceFields(text, [field('patient_name', 'text', 'Dana')]);

    expect(layoutLines(text, marks)).toEqual([
      { number: 1, segments: [{ text: 'Patient: ' }, { text: 'Dana', keys: ['patient_name'] }] },
      { number: 2, segments: [] },
      { number: 3, segments: [{ text: 'Total: $10' }] },
    ]);
  });
});

describe('describeTrace', () => {
  it('names the lines a value was found on', () => {
    expect(describeTrace({ status: 'found', lines: [4] })).toBe('Line 4');
    expect(describeTrace({ status: 'found', lines: [4, 8] })).toBe('Lines 4 and 8');
    expect(describeTrace({ status: 'found', lines: [2, 5, 9] })).toBe('Lines 2, 5, and 9');
    expect(describeTrace({ status: 'not-found', lines: [] })).toBe('Not in this document');
    expect(describeTrace({ status: 'missing', lines: [] })).toBe('Missing');
  });
});

describe('needlesFor', () => {
  it('lists the printed forms of an amount', () => {
    expect(needlesFor('currency', 72000)).toEqual(['72,000.00', '72000.00', '72,000', '72000']);
  });
});
