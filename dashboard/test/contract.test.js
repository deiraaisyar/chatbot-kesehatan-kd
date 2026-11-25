import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assessmentSchema, features, formatNumber, validateAssessment } from '../src/assessment.js';
import { createPiApi, normalizeUrl } from '../src/api.js';
import { createDemoApi, examples } from '../src/demo.js';

function formFor(input) {
  return new Map(Object.entries(input).map(([key, value]) => [key, value == null ? '' : String(value)]));
}

test('assessment validation accepts decimal comma and sends exactly the v1 fields', () => {
  for (const { input } of Object.values(examples)) {
    const form = formFor(input);
    form.set('bmi', formatNumber(input.bmi));
    form.set('height', '170');
    form.set('weight', '63');
    assert.deepEqual(validateAssessment(form, features), { errors: {}, payload: input });
  }
});

test('validation handles required fields, invalid data, and limits from metadata', () => {
  const form = formFor({ ...examples.low.input, age: 32.5, bmi: '2e1', hdl: '', sbp: 140, dbp: 150, male: 2 });
  const schema = assessmentSchema({ features: [{ name: 'sbp', type: 'float', max: 130 }] });
  const { payload, errors } = validateAssessment(form, schema);
  assert.deepEqual(Object.keys(errors).sort(), ['age', 'bmi', 'hdl', 'male', 'sbp']);
  assert.equal(payload.dbp, 150);
});

test('demo returns its fixed missing, low, and emergency cards and supports chat cancellation', async () => {
  const api = createDemoApi();
  for (const [key, { input, risiko }] of Object.entries(examples)) {
    const { card } = await api.assess(input);
    assert.deepEqual(card.risiko, risiko);
    if (key === 'missing') assert.deepEqual(card.data_tidak_lengkap, ['fam_dm', 'fam_mi']);
    if (key === 'red') assert.match(card.peringatan[0], /sangat tinggi/);
  }
  const { assessment_id } = await api.assess(examples.low.input);
  const signal = AbortSignal.abort();
  await assert.rejects(api.chat(assessment_id, { session_id: null, message: 'Contoh' }, signal), { name: 'AbortError' });
  const chat = await api.chat(assessment_id, { session_id: null, message: 'Contoh' });
  assert.equal(chat.turn, 1);
  assert.equal(chat.fallback, true);
  await assert.rejects(api.assess({ ...examples.low.input, age: 36 }), { code: 'demo_input' });
});

test('API sends the expected methods, auth headers, and error details', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async (url) => {
    if (url.endsWith('/chat')) {
      return new Response(JSON.stringify({ error: { code: 'rate_limited', message: 'Coba lagi' }, request_id: 'req_test' }), { status: 429, headers: { 'Retry-After': '5' } });
    }
    return Response.json({ status: 'ok' });
  });
  const api = createPiApi('http://192.168.50.2:8000', 'test-token');
  await api.health();
  await api.meta();
  const body = { session_id: 'session-fixture', message: 'Pertanyaan sintetis' };
  await assert.rejects(api.chat('card/1', body), { status: 429, code: 'rate_limited', requestId: 'req_test', retryAfter: 5 });
  const [health, meta, chat] = fetch.mock.calls.map(({ arguments: args }) => args);
  assert.equal(health[0], 'http://192.168.50.2:8000/v1/health');
  assert.equal(health[1].headers.Authorization, undefined);
  assert.equal(meta[1].headers.Authorization, 'Bearer test-token');
  assert.equal(meta[1].headers['X-Client-Version'], '1.0.0');
  assert.ok(chat[0].endsWith('/assessments/card%2F1/chat'));
  assert.deepEqual(JSON.parse(chat[1].body), body);
});

test('configured URLs never contain embedded credentials or query data', () => {
  assert.equal(normalizeUrl(' http://192.168.50.2:8000/ '), 'http://192.168.50.2:8000');
  for (const invalid of ['ftp://pi', 'http://user:secret@pi', 'http://pi/?token=something', 'http://pi/#data']) {
    assert.throws(() => normalizeUrl(invalid));
  }
});
