export const features = [
  { name: 'age', label: 'Umur', type: 'int', required: true, min: 18, max: 120, unit: 'tahun' },
  { name: 'male', label: 'Jenis kelamin', type: 'binary', required: true },
  { name: 'bmi', label: 'BMI', type: 'float', required: true, min: 10, max: 80, unit: 'kg/m²' },
  { name: 'sbp', label: 'Sistolik', type: 'float', required: true, min: 70, max: 260, unit: 'mmHg' },
  { name: 'dbp', label: 'Diastolik', type: 'float', required: true, min: 40, max: 150, unit: 'mmHg' },
  { name: 'smoker', label: 'Pernah merokok (≥100 batang seumur hidup)', type: 'binary', required: false },
  { name: 'waist', label: 'Lingkar pinggang', type: 'float', required: false, min: 40, max: 200, unit: 'cm' },
  { name: 'hdl', label: 'Kolesterol HDL', type: 'float', required: true, min: 10, max: 200, unit: 'mg/dL' },
  { name: 'fam_dm', label: 'Riwayat diabetes pada keluarga dekat', type: 'binary', required: false },
  { name: 'fam_mi', label: 'Riwayat serangan jantung pada keluarga dekat', type: 'binary', required: false },
  { name: 'vig_rec', label: 'Olahraga berat (rekreasi rutin)', type: 'binary', required: false },
  { name: 'mod_rec', label: 'Olahraga sedang (rekreasi rutin)', type: 'binary', required: false },
];

export const missingLabels = {
  age: 'Umur', male: 'Jenis kelamin', bmi: 'BMI', sbp: 'Tekanan darah sistolik', dbp: 'Tekanan darah diastolik',
  smoker: 'Status merokok', waist: 'Lingkar pinggang', hdl: 'HDL', fam_dm: 'Riwayat diabetes keluarga',
  fam_mi: 'Riwayat serangan jantung keluarga', vig_rec: 'Olahraga berat', mod_rec: 'Olahraga sedang',
};

export const diseases = {
  hipertensi: ['Hipertensi', 'Tekanan darah tinggi (NHANES BPQ020)'],
  diabetes: ['Diabetes', 'Riwayat atau kriteria glukosa/HbA1c'],
  kolesterol_tinggi: ['Kolesterol tinggi', 'Riwayat kolesterol tinggi (NHANES BPQ080)'],
};

const decimal = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 10, useGrouping: false });
export const formatNumber = (value) => value == null ? '—' : decimal.format(value);

export function parseNumber(input) {
  const text = input.trim();
  return /^\d+(?:[.,]\d+)?$/.test(text) ? Number(text.replace(',', '.')) : NaN;
}

export function assessmentSchema(meta) {
  const byName = new Map((meta?.features ?? []).map((feature) => [feature.name, feature]));
  return features.map((feature) => {
    const update = byName.get(feature.name);
    // The twelve v1 keys and form controls are fixed. The Pi may supply new labels and limits.
    return update?.type === feature.type ? { ...feature, ...update } : feature;
  });
}

export function validateAssessment(values, schema) {
  const payload = {};
  const errors = {};
  for (const { name, type, required, min, max, unit } of schema) {
    const raw = String(values.get(name) ?? '').trim();
    if (!raw) {
      if (required) errors[name] = 'Wajib diisi.';
      else payload[name] = null;
      continue;
    }
    if (type === 'binary') {
      if (raw === '0' || raw === '1') payload[name] = Number(raw);
      else errors[name] = 'Pilih salah satu opsi.';
      continue;
    }

    const value = parseNumber(raw);
    if (!Number.isFinite(value)) errors[name] = 'Masukkan angka yang valid.';
    else if (type === 'int' && !Number.isInteger(value)) errors[name] = 'Gunakan bilangan bulat.';
    else if (value < min || value > max) errors[name] = `Masukkan nilai antara ${min} dan ${max}${unit ? ` ${unit}` : ''}.`;
    else payload[name] = value;
  }
  return { payload, errors };
}
