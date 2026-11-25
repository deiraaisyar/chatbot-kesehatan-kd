import { diseases, formatNumber, missingLabels } from './assessment.js';
import { $, element, icon } from './dom.js';

const riskIcons = { rendah: 'check_circle', sedang: 'warning', tinggi: 'error' };
const dateTime = new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
const measure = (value, unit) => value == null ? '—' : `${formatNumber(value)} ${unit}`;

function definition(label, value, className = '', valueClass = '') {
  const group = element('div', className);
  group.append(element('dt', '', label), element('dd', valueClass, value));
  return group;
}

function riskRow(key, entry) {
  const [name, description] = diseases[key];
  const row = element('div', 'risk-row');
  const label = element('div');
  label.append(element('p', 'risk-name', name), element('p', 'text-small muted', description));
  const metrics = element('div', 'risk-metrics');
  const level = entry.tingkat;
  const chip = element('span', 'chip');
  if (Object.hasOwn(riskIcons, level)) {
    chip.classList.add(level);
    chip.append(icon(riskIcons[level]));
  }
  chip.append(element('span', '', level));
  metrics.append(element('span', 'risk-value', entry.persen_perkiraan), chip);
  row.append(label, metrics);
  return row;
}

function replaceList(id, messages) {
  $(id).replaceChildren(...messages.map((message) => element('li', '', message)));
}

export function renderResult(assessment, mode, expired = false) {
  $('result-empty').hidden = Boolean(assessment);
  $('result-empty-text').textContent = expired ? 'Hasil sudah kedaluwarsa. Silakan hitung ulang.' : 'Isi formulir penilaian untuk melihat perkiraan risiko.';
  $('result-content').hidden = !assessment;
  $('assessment-id').hidden = !assessment;
  $('assessment-id').textContent = assessment?.assessment_id ?? '';
  $('emergency').hidden = true;
  $('other-warnings').hidden = true;
  if (!assessment) {
    $('result-meta').textContent = '';
    for (const id of ['emergency-text', 'patient-summary', 'risk-rows', 'categories', 'warning-list', 'missing-list', 'result-disclaimer']) $(id).replaceChildren();
    return;
  }

  const { card, expires_at, versions } = assessment;
  const { pasien, kategori, risiko } = card;
  const expiry = Date.parse(expires_at);
  const source = mode === 'demo' ? 'Skenario demo' : versions?.risk || 'Raspberry Pi';
  $('result-meta').textContent = Number.isFinite(expiry) ? `${source} · Berlaku hingga ${dateTime.format(expiry)}` : source;

  const emergencyWarnings = [];
  const otherWarnings = [];
  for (const warning of card.peringatan) {
    (warning.toLowerCase().includes('sangat tinggi') ? emergencyWarnings : otherWarnings).push(warning);
  }
  replaceList('emergency-text', emergencyWarnings);
  $('emergency').hidden = emergencyWarnings.length === 0;
  replaceList('warning-list', otherWarnings);
  $('other-warnings').hidden = otherWarnings.length === 0;

  const pressure = `${formatNumber(pasien.td_sistolik)}/${formatNumber(pasien.td_diastolik)}`;
  $('patient-summary').replaceChildren(
    definition('Umur', measure(pasien.umur, 'th')),
    definition('Kelamin', pasien.jenis_kelamin),
    definition('BMI', measure(pasien.bmi, 'kg/m²')),
    definition('Tekanan darah', `${pressure} mmHg`, '', emergencyWarnings.length ? 'critical' : ''),
    definition('Pinggang', measure(pasien.lingkar_pinggang_cm, 'cm')),
    definition('HDL', measure(pasien.hdl_mgdl, 'mg/dL')),
  );
  $('risk-rows').replaceChildren(...Object.keys(diseases).filter((key) => risiko[key]).map((key) => riskRow(key, risiko[key])));
  $('categories').replaceChildren(
    definition('Tekanan darah', kategori.tekanan_darah, 'panel'),
    definition('BMI (Asia-Pasifik)', kategori.bmi, 'panel'),
    definition('Lingkar pinggang', kategori.lingkar_pinggang, 'panel'),
    definition('HDL', kategori.hdl, 'panel'),
  );
  const missing = card.data_tidak_lengkap.map((key) => missingLabels[key] ?? key);
  replaceList('missing-list', missing.length ? missing : ['Semua data penilaian terisi.']);
  $('result-disclaimer').textContent = card.disclaimer;
}
