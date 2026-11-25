import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { createDemoApi, examples } from '../src/demo.js';

const url = process.env.PROTOTYPE_URL || 'http://127.0.0.1:4173/';
const origin = new URL(url).origin;
const browser = await chromium.launch(process.env.PROTOTYPE_BROWSER ? { executablePath: process.env.PROTOTYPE_BROWSER } : { channel: 'msedge' });
const output = new URL('../test-results/', import.meta.url);
await mkdir(output, { recursive: true });

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const external = [];
  const runtimeErrors = [];
  page.on('pageerror', (error) => runtimeErrors.push(error.message));
  await page.route('**/*', async (route) => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    external.push(route.request().url());
    await route.abort();
  });
  const visible = (selector) => page.locator(selector).waitFor({ state: 'visible' });
  const text = async (selector, fragment) => assert.match(await page.locator(selector).innerText(), fragment);
  const screenshot = async (name) => {
    const path = new URL(`${name}.png`, output);
    await page.screenshot({ path: fileURLToPath(path), fullPage: true });
  };
  const loadCase = async (scenario) => {
    await page.getByRole('link', { name: 'Penilaian', exact: true }).click();
    await page.locator('#demo-case').selectOption(scenario);
    await page.locator('#load-case').click();
    await page.getByRole('button', { name: 'Hitung risiko' }).click();
    await visible('#result-content');
  };

  await page.goto(url);
  await page.locator('#apply-bmi').click();
  assert.equal(await page.locator('#bmi').inputValue(), '24,6');
  await screenshot('01-penilaian');
  await page.locator('#age').fill('17');
  await page.getByRole('button', { name: 'Hitung risiko' }).click();
  await visible('#error-age');
  assert.equal(await page.locator('#age').evaluate((node) => node === document.activeElement), true);

  await loadCase('missing');
  await text('#missing-list', /Riwayat diabetes keluarga/);
  await text('#missing-list', /Riwayat serangan jantung keluarga/);
  await loadCase('low');
  assert.deepEqual(await page.locator('.risk-value').allTextContents(), ['5%', '<5%', '15%']);
  await loadCase('red');
  await visible('#emergency');
  await text('#emergency-text', /tekanan darah sangat tinggi/);

  await page.getByRole('button', { name: 'Tanya tentang hasil ini' }).click();
  assert.equal(await page.locator('#chat-input').evaluate((node) => node === document.activeElement), true);
  await page.getByRole('button', { name: 'Tolong jelaskan hasil saya.' }).click();
  await page.getByRole('button', { name: 'Kirim', exact: true }).click();
  await page.getByRole('button', { name: 'Hentikan' }).click();
  await page.getByText('Permintaan dihentikan.', { exact: true }).waitFor();
  assert.equal(await page.locator('.bubble').count(), 0);
  await page.getByRole('button', { name: 'Kirim', exact: true }).click();
  await visible('.bubble .fallback');
  await text('#chat-status', /1\/6/);
  await text('#result-disclaimer', /bukan diagnosis/);
  await screenshot('02-hasil-dan-chat');
  await page.getByRole('button', { name: 'Sesi baru', exact: true }).click();
  assert.equal(await page.locator('.bubble').count(), 0);

  await page.getByRole('link', { name: 'Pengaturan', exact: true }).click();
  await visible('#settings-title');
  await screenshot('03-pengaturan');
  await page.getByRole('button', { name: 'Hapus data sesi lokal' }).click();
  await visible('#clear-feedback');
  await page.getByRole('link', { name: 'Kartu Hasil', exact: true }).click();
  await visible('#result-empty');
  await page.getByRole('link', { name: 'Penilaian', exact: true }).click();
  assert.equal(await page.locator('#age').inputValue(), '');
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await screenshot('04-penilaian-mobile');
  await page.reload();
  assert.equal(await page.locator('#age').inputValue(), '19');
  assert.deepEqual(external, []);

  const mock = createDemoApi();
  const health = await mock.health();
  const meta = await mock.meta();
  const sample = await mock.assess(examples.low.input);
  let behavior = 'offline';
  const payloads = [];
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (behavior === 'offline') return route.abort();
    if (path === '/v1/health') {
      assert.equal(request.headers().authorization, undefined);
      return route.fulfill({ json: { ...health, chat: { available: behavior !== 'chat-down' } } });
    }
    assert.equal(request.headers().authorization, 'Bearer token-uji-sintetis');
    if (path === '/v1/meta') return route.fulfill({ json: { ...meta, chat: { ...meta.chat, multi_turn: false, max_turns: 1 } } });
    if (path === '/v1/assessments') {
      payloads.push(request.postDataJSON());
      if (behavior === 'field-error') return route.fulfill({ status: 422, json: { error: { code: 'validation_error', message: 'Input tidak valid', fields: { sbp: 'Nilai ditolak oleh API uji' } } } });
      return route.fulfill({ status: 201, json: sample });
    }
    payloads.push(request.postDataJSON());
    return route.fulfill({ json: { session_id: 'cht_sintetis', answer: 'Jawaban API uji.', turn: 1, guard: { ok: true, flags: [] }, fallback: false } });
  });
  await page.getByRole('link', { name: 'Pengaturan', exact: true }).click();
  await page.getByText('Raspberry Pi', { exact: true }).click();
  await page.locator('#api-url').fill(origin);
  await page.locator('#token').fill('token-uji-sintetis');
  await page.getByRole('button', { name: 'Tes koneksi' }).click();
  await page.getByText('Tidak dapat terhubung ke Raspberry Pi.', { exact: false }).first().waitFor();
  behavior = 'chat-down';
  await page.getByRole('button', { name: 'Coba lagi' }).click();
  await page.getByText('Fitur tanya jawab belum tersedia.', { exact: false }).first().waitFor();
  await page.getByRole('link', { name: 'Penilaian', exact: true }).click();
  for (const [key, value] of Object.entries(examples.low.input)) {
    const number = page.locator(`#${key}`);
    if (await number.count()) await number.fill(String(value));
    else await page.locator(`label:has(input[name="${key}"][value="${value}"])`).click();
  }
  behavior = 'field-error';
  await page.getByRole('button', { name: 'Hitung risiko' }).click();
  await visible('#error-sbp');
  await text('#error-sbp', /Nilai ditolak oleh API uji/);
  assert.deepEqual(payloads[0], examples.low.input);

  behavior = 'online';
  await page.getByRole('button', { name: 'Coba lagi' }).click();
  await page.locator('#global-banner').waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: 'Hitung risiko' }).click();
  await visible('#result-content');
  await text('#chat-title', /Tanya satu pertanyaan/);
  await page.locator('#chat-input').fill('Pertanyaan uji');
  await page.getByRole('button', { name: 'Kirim', exact: true }).click();
  await page.getByText('Jawaban API uji.', { exact: true }).waitFor();
  assert.deepEqual(payloads.at(-1), { session_id: null, message: 'Pertanyaan uji' });
  await text('#chat-status', /Sesi berakhir/);
  assert.equal(await page.locator('#chat-input').isDisabled(), true);
  const storage = await page.evaluate(() => Object.entries(localStorage));
  assert.deepEqual(storage.map(([key]) => key).sort(), ['kartu-risiko-pi:endpoint', 'kartu-risiko-pi:mode']);
  assert.ok(!JSON.stringify(storage).includes('token-uji-sintetis'));
  assert.deepEqual(runtimeErrors, []);
  console.log('E2E lulus: 3 skenario offline, form/BMI, chat dan batal, reset, mobile, 422, fallback koneksi, dan kontrak Pi tiruan.');
} finally {
  await browser.close();
}
