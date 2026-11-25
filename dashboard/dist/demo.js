import { features } from './assessment.js';
import { ApiError } from './api.js';

export const disclaimer = 'Hasil ini adalah perkiraan risiko statistik dari data survei dewasa Amerika (NHANES), bukan diagnosis. Konsultasikan dengan dokter atau tenaga kesehatan untuk pemeriksaan dan keputusan medis.';
const risks = (hipertensi, diabetes, kolesterol_tinggi) => ({ hipertensi, diabetes, kolesterol_tinggi });
const risk = (probabilitas, persen_perkiraan, tingkat = 'rendah') => ({ probabilitas, persen_perkiraan, tingkat });
const demoVersions = { risk: 'data-contoh', chat: 'jawaban-contoh' };

export const examples = {
  low: {
    input: { age: 35, male: 1, bmi: 25.2, sbp: 119, dbp: 68, smoker: 0, waist: 88, hdl: 46, fam_dm: 0, fam_mi: 0, vig_rec: 1, mod_rec: 1 },
    kategori: { tekanan_darah: 'normal', bmi: 'obesitas I', lingkar_pinggang: 'normal', hdl: 'cukup' },
    risiko: risks(risk(0.062, '5%'), risk(0.009, '<5%'), risk(0.143, '15%')),
    answer: 'Kartu contoh ini menampilkan tingkat rendah untuk ketiga kondisi. Persentase di kartu adalah perkiraan dari skenario demo.',
  },
  missing: {
    input: { age: 19, male: 0, bmi: 24.6, sbp: 98, dbp: 66, smoker: 0, waist: 76.9, hdl: 60, fam_dm: null, fam_mi: null, vig_rec: 1, mod_rec: 0 },
    kategori: { tekanan_darah: 'normal', bmi: 'berat badan lebih', lingkar_pinggang: 'normal', hdl: 'cukup' },
    risiko: risks(risk(0.021, '<5%'), risk(0.008, '<5%'), risk(0.09, '10%')),
    answer: 'Pada kartu contoh ini ketiga risiko ditampilkan dengan tingkat rendah. Riwayat diabetes dan serangan jantung pada keluarga tercatat sebagai data yang tidak diisi.',
  },
  red: {
    input: { age: 58, male: 1, bmi: 25.1, sbp: 185, dbp: 121, smoker: 1, waist: 92.8, hdl: 45, fam_dm: 0, fam_mi: 0, vig_rec: 0, mod_rec: 0 },
    kategori: { tekanan_darah: 'hipertensi stage 2', bmi: 'obesitas I', lingkar_pinggang: 'di atas batas (obesitas sentral)', hdl: 'cukup' },
    risiko: risks(risk(0.97, '>95%', 'tinggi'), risk(0.25, '25%', 'sedang'), risk(0.45, '45%', 'sedang')),
    peringatan: ['tekanan darah sangat tinggi: anjurkan segera ke fasilitas kesehatan'],
    answer: 'Risiko hipertensi pada kartu contoh ini ditampilkan sebagai tinggi (>95%). Peringatan tekanan darah dari skenario ini tercantum di bagian atas kartu.',
  },
};

const defaultChat = { available: true, multi_turn: true, max_turns: 6, session_ttl_seconds: 1800 };

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    signal?.throwIfAborted();
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, ms);
    function abort() {
      clearTimeout(timer);
      reject(signal.reason);
    }
    signal?.addEventListener('abort', abort, { once: true });
  });
}

const yesNo = (value) => value === 1 ? 'ya' : value === 0 ? 'tidak' : 'tidak tahu';

export function createDemoApi() {
  let current;
  let sessions = new Map();

  return {
    health: async () => ({
      status: 'ok', risk: risks('ok', 'ok', 'ok'), chat: { available: true, backend: 'demo' }, versions: demoVersions,
    }),
    meta: async () => ({ api_version: '1.0', features, chat: defaultChat, disclaimer }),
    async assess(input, signal) {
      await wait(200, signal);
      const scenario = Object.values(examples).find(({ input: example }) => features.every(({ name }) => example[name] === input[name]));
      if (!scenario) throw new ApiError('Mode demo menggunakan tiga set data contoh. Tekan Isi contoh untuk memuat skenario, atau hubungkan Raspberry Pi untuk menilai data lain.', { code: 'demo_input' });

      const { age, male, bmi, sbp, dbp, smoker, waist, hdl, fam_dm, fam_mi, vig_rec, mod_rec } = scenario.input;
      const now = Date.now();
      const assessment_id = `asm_demo_${now.toString(36)}`;
      current = { id: assessment_id, scenario, expires: now + 7_200_000 };
      sessions = new Map();
      return {
        assessment_id, created_at: new Date(now).toISOString(), expires_at: new Date(current.expires).toISOString(),
        probabilities: Object.fromEntries(Object.entries(scenario.risiko).map(([key, entry]) => [key, entry.probabilitas])),
        card: {
          versi: 1,
          pasien: {
            umur: age, jenis_kelamin: male === 1 ? 'laki-laki' : 'perempuan', bmi, td_sistolik: sbp, td_diastolik: dbp,
            pernah_merokok: yesNo(smoker), lingkar_pinggang_cm: waist, hdl_mgdl: hdl,
            riwayat_diabetes_keluarga: yesNo(fam_dm), riwayat_serangan_jantung_keluarga: yesNo(fam_mi),
            olahraga_berat_rekreasi: yesNo(vig_rec), olahraga_sedang_rekreasi: yesNo(mod_rec),
          },
          kategori: scenario.kategori, risiko: scenario.risiko, peringatan: scenario.peringatan ?? [],
          data_tidak_lengkap: Object.keys(scenario.input).filter((key) => scenario.input[key] === null), disclaimer,
        },
        versions: demoVersions,
      };
    },
    async chat(id, { session_id }, signal) {
      await wait(900, signal);
      const now = Date.now();
      if (id !== current?.id || current.expires <= now) throw new ApiError('Hasil sudah kedaluwarsa.', { status: 410, code: 'assessment_not_found' });
      const session = session_id ? sessions.get(session_id) : { id: `cht_demo_${now.toString(36)}`, turn: 0, expires: now + 1_800_000 };
      if (!session || session.expires <= now) throw new ApiError('Sesi tanya jawab berakhir.', { status: 410, code: 'session_not_found' });
      if (session.turn >= defaultChat.max_turns) throw new ApiError('Batas pertanyaan tercapai.', { status: 409, code: 'turn_limit_reached' });
      session.turn += 1;
      sessions.set(session.id, session);
      return {
        session_id: session.id, answer: `${current.scenario.answer}\n\n${disclaimer}`, turn: session.turn,
        guard: { ok: true, flags: [] }, fallback: true, model_version: demoVersions.chat,
      };
    },
  };
}
