import { APP_VERSION, ApiError, DEFAULT_URL, createPiApi, normalizeUrl } from './api.js';
import { assessmentSchema, diseases, validateAssessment } from './assessment.js';
import { createDemoApi, disclaimer, examples } from './demo.js';
import { $, clearFeedback, element, showFeedback } from './dom.js';
import { mountFields, setForm, showFieldErrors, updateFields } from './form.js';
import { renderResult } from './result.js';

const unavailable = 'Fitur tanya jawab belum tersedia. Anda tetap dapat melihat hasil risiko.';
const ended = 'Sesi tanya jawab berakhir. Silakan mulai sesi baru.';
const limit = 'Batas pertanyaan untuk sesi ini tercapai. Mulai sesi baru untuk melanjutkan.';
const views = { penilaian: 'assessment-title', hasil: 'result-title', pengaturan: 'settings-title' };
const questions = [
  'Tolong jelaskan hasil saya.', 'Kenapa risiko hipertensi saya tinggi?',
  'Apa yang bisa saya lakukan untuk menurunkan risiko?', 'Apakah saya perlu ke dokter?', 'Seberapa akurat hasil ini?',
];

const connectionForm = $('connection-form');
const form = $('assessment-form');
const transcript = $('chat-transcript');
const chatInput = $('chat-input');
const suggestionButtons = questions.map((question) => {
  const button = element('button', 'button small', question);
  button.type = 'button';
  button.addEventListener('click', () => {
    chatInput.value = question;
    updateComposer();
    chatInput.focus();
  });
  return button;
});
$('suggestions').append(...suggestionButtons);

function saved(key) {
  try { return localStorage.getItem(`kartu-risiko-pi:${key}`); } catch { return null; }
}

function saveSetting(key, value) {
  try { localStorage.setItem(`kartu-risiko-pi:${key}`, value); } catch { /* Temporary mode remains usable. */ }
}

let mode = saved('mode') === 'pi' ? 'pi' : 'demo';
let apiUrl = DEFAULT_URL;
try { apiUrl = normalizeUrl(saved('endpoint') ?? DEFAULT_URL); } catch { /* Use the default endpoint. */ }
let token = '';
let api = createDemoApi();
let schema = assessmentSchema();
let health = null;
let meta = null;
let checking = null;
let connectionError = null;
let assessment = null;
let assessmentExpiry;
let assessmentRequest = null;
let chatUnavailable = false;
let chatRequest = null;
let chatTimer;
let rateTimer;
let rateLimitedUntil = 0;
let session = { id: null, turn: 0, closed: false };
let view;

function showView(focus = true) {
  const target = location.hash.slice(1);
  view = Object.hasOwn(views, target) ? target : 'penilaian';
  $('workbench').hidden = view === 'pengaturan';
  for (const name of Object.keys(views)) $(name).hidden = name !== view;
  for (const link of document.querySelectorAll('.nav a, .topbar-end a')) {
    if (link.dataset.view === view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (focus) {
    window.scrollTo(0, 0);
    $(views[view]).focus({ preventScroll: true });
  }
}

function navigate(next) {
  if (location.hash === `#${next}`) showView();
  else location.hash = next;
}

function riskReady() {
  return Boolean(meta && health && health.status !== 'down' && Object.keys(diseases).every((key) => health.risk?.[key] === 'ok'));
}

function chatReady() {
  return Boolean(!chatUnavailable && !checking && !connectionError && health?.status !== 'down' && health?.chat?.available && meta?.chat?.available);
}

function refreshAssessment() {
  $('assessment-controls').disabled = Boolean(checking || assessmentRequest || !riskReady());
  $('submit-label').textContent = assessmentRequest ? 'Menghitung…' : 'Hitung risiko';
}

function refreshSettings() {
  const piSelected = connectionForm.elements.mode.value === 'pi';
  $('pi-fields').hidden = !piSelected;
  $('test-connection').disabled = Boolean(checking);
  for (const control of connectionForm.elements.mode) control.disabled = Boolean(checking);
  $('test-label').textContent = checking ? 'Menguji…' : piSelected ? 'Tes koneksi' : 'Gunakan mode demo';
}

function modelRow(name, status, detail) {
  const row = element('div', 'model-row');
  const title = element('div');
  title.append(element('p', 'mono', name));
  if (detail) title.append(element('p', 'text-small muted', detail));
  const tone = { Siap: 'rendah', 'Belum siap': 'tinggi', Simulasi: 'rendah' }[status] ?? '';
  row.append(title, element('span', `chip ${tone}`, status));
  return row;
}

function refreshConnection() {
  let tone = 'ready';
  let message = '';
  let label = `Pi ${new URL(apiUrl).hostname}`;
  if (checking) {
    tone = 'checking';
    label = 'Menghubungkan';
    message = 'Menghubungkan ke Raspberry Pi…';
  } else if (mode === 'demo') {
    tone = 'demo';
    label = 'Mode demo';
    message = 'Gunakan data contoh untuk mencoba penilaian dan tanya jawab. Hubungkan Raspberry Pi di Pengaturan untuk menilai data lain.';
  } else if (connectionError) {
    tone = 'offline';
    label = connectionError.status === 401 ? 'Token diperlukan' : 'Pi terputus';
    message = connectionError.message;
  } else if (!riskReady()) {
    tone = 'warn';
    label = 'Pi belum siap';
    message = 'Model risiko di Raspberry Pi belum siap. Coba lagi setelah layanan tersedia.';
  } else if (!chatReady()) {
    tone = 'warn';
    message = unavailable;
  } else if (health.status === 'degraded') {
    tone = 'warn';
    message = 'Sebagian layanan di Raspberry Pi sedang mengalami gangguan.';
  }
  $('connection-badge').dataset.tone = tone;
  $('connection-label').textContent = label;
  $('connection-version').textContent = mode === 'pi' && !checking && !connectionError ? health?.versions?.risk ?? '' : '';
  $('global-banner').dataset.tone = tone;
  $('global-banner').hidden = !message;
  $('global-message').textContent = message;
  $('reconnect').hidden = !['offline', 'warn'].includes(tone) || connectionError?.status === 401;
  $('banner-settings').hidden = !['warn', 'offline'].includes(tone);
  $('demo-tools').hidden = mode !== 'demo';
  $('assessment-privacy').textContent = mode === 'demo' ? 'Mode demo memakai data contoh selama sesi ini.' : 'Data penilaian dikirim ke API Raspberry Pi dan hanya disimpan di tab ini selama sesi.';

  $('api-version').textContent = meta?.api_version ? `v${meta.api_version}` : '—';
  const models = Object.keys(diseases).map((key) => modelRow(`${key}.onnx`, mode === 'demo' ? 'Simulasi' : !health ? 'Belum diperiksa' : health.risk?.[key] === 'ok' ? 'Siap' : 'Belum siap'));
  const chatName = mode === 'demo' ? 'Jawaban contoh' : health?.versions?.chat || health?.chat?.backend || 'Chat lokal';
  models.push(modelRow(chatName, mode === 'demo' ? 'Simulasi' : !health ? 'Belum diperiksa' : chatReady() ? 'Siap' : 'Belum siap',
    chatReady() ? meta.chat.multi_turn ? `Multi-turn · maks ${meta.chat.max_turns} pertanyaan` : 'Satu pertanyaan per sesi' : ''));
  $('model-status').replaceChildren(...models);
  refreshSettings();
  refreshAssessment();
  refreshChat();
}

function authError() {
  token = '';
  $('token').value = '';
  meta = null;
  connectionError = new ApiError('Masukkan bearer token Raspberry Pi yang valid di Pengaturan.', { status: 401 });
  $('connection-feedback').textContent = connectionError.message;
  navigate('pengaturan');
  refreshConnection();
}

async function connect(nextMode, nextUrl = apiUrl, nextToken = token, interactive = false) {
  if (checking) return;
  const changed = [nextMode, nextUrl, nextToken].some((value, index) => value !== [mode, apiUrl, token][index]);
  mode = nextMode;
  apiUrl = nextUrl;
  token = nextToken;
  saveSetting('mode', mode);
  saveSetting('endpoint', apiUrl);
  if (changed) {
    resetAssessment();
    if (mode === 'demo') loadExample();
  }
  if (mode === 'pi') api = createPiApi(apiUrl, token);
  else {
    token = '';
    $('token').value = '';
  }
  const controller = new AbortController();
  checking = controller;
  connectionError = null;
  health = null;
  meta = null;
  const feedback = $('connection-feedback');
  feedback.textContent = 'Memeriksa koneksi…';
  refreshConnection();
  const start = performance.now();

  try {
    health = await api.health(controller.signal);
    meta = await api.meta(controller.signal);
    schema = assessmentSchema(meta);
    updateFields(schema);
    chatUnavailable = false;
    feedback.textContent = mode === 'demo' ? 'Data contoh siap digunakan.' : `API merespons (${Math.round(performance.now() - start)} ms).`;
    if (interactive && mode === 'demo') navigate('penilaian');
  } catch (error) {
    connectionError = error;
    feedback.textContent = error.message;
    if (error.status === 401) authError();
  } finally {
    checking = null;
    refreshConnection();
  }
}

function clearSession() {
  chatRequest?.abort();
  chatRequest = null;
  clearTimeout(chatTimer);
  session = { id: null, turn: 0, closed: false };
  transcript.replaceChildren();
  transcript.hidden = true;
  chatInput.value = '';
  clearFeedback($('chat-feedback'));
}

function clearAssessment(expired = false) {
  clearTimeout(assessmentExpiry);
  assessment = null;
  clearSession();
  clearTimeout(rateTimer);
  rateLimitedUntil = 0;
  renderResult(null, mode, expired);
  refreshChat();
}

function resetAssessment() {
  assessmentRequest?.abort();
  assessmentRequest = null;
  clearAssessment();
  if (mode === 'demo') api = createDemoApi();
  setForm(null, schema);
  refreshAssessment();
}

function loadExample() {
  resetAssessment();
  setForm(examples[$('demo-case').value].input, schema);
}

function displayAssessment(next) {
  clearAssessment();
  assessment = next;
  renderResult(assessment, mode);
  const expiry = Date.parse(next.expires_at);
  if (Number.isFinite(expiry)) assessmentExpiry = setTimeout(() => clearAssessment(true), Math.max(0, expiry - Date.now()));
  refreshChat();
  if (view !== 'pengaturan') navigate('hasil');
}

function showAssessmentError(error) {
  if (error.status === 401) return authError();
  if ([400, 422].includes(error.status) && showFieldErrors(error.fields ?? {})) return;
  const node = $('assessment-error');
  showFeedback(node, error.status >= 500 && error.status !== 504 ? 'Penilaian belum dapat diproses. Silakan coba lagi.' : error.message, { error: true, requestId: error.requestId });
  node.focus();
}

function maxTurns() { return meta?.chat?.multi_turn ? meta.chat.max_turns : 1; }

function updateComposer() {
  $('char-count').textContent = `${chatInput.value.length}/500`;
  $('send-chat').disabled = chatInput.disabled || !chatInput.value.trim();
}

function refreshChat() {
  const available = chatReady();
  const ready = Boolean(assessment && available);
  const blocked = Boolean(!ready || chatRequest || session.closed || Date.now() < rateLimitedUntil);
  const minutes = Math.ceil((meta?.chat?.session_ttl_seconds ?? 0) / 60);
  const status = !assessment ? 'Menunggu kartu' : !available ? 'Tanya jawab belum tersedia' :
    session.closed ? 'Sesi berakhir' : `Pertanyaan ${session.turn}/${maxTurns()}${minutes ? ` · Sesi ${minutes} menit` : ''}`;
  $('chat-title-label').textContent = ready && !meta.chat.multi_turn ? 'Tanya satu pertanyaan tentang hasil' : 'Tanya tentang hasil';
  $('chat-status').textContent = status;
  $('chat-empty').hidden = ready && !transcript.hidden;
  $('chat-empty-title').textContent = !assessment ? 'Kartu hasil belum tersedia' : available ? 'Mulai tanya jawab' : 'Tanya jawab belum tersedia';
  $('chat-empty-text').textContent = !assessment ? 'Isi formulir lalu tekan Hitung risiko untuk mulai bertanya tentang kartu hasil.' :
    available ? 'Pilih saran atau tulis pertanyaan tentang kartu ini.' : unavailable;
  $('chat-disclaimer').textContent = assessment?.card?.disclaimer || meta?.disclaimer || disclaimer;
  $('new-session').hidden = !ready;
  $('focus-chat').hidden = !ready;
  $('suggestion-area').hidden = !ready;
  $('stop-chat').hidden = !chatRequest;
  for (const button of suggestionButtons) button.disabled = blocked;
  chatInput.disabled = blocked;
  chatInput.placeholder = !assessment ? 'Hitung risiko terlebih dahulu untuk bertanya…' : available ? 'Tulis pertanyaan tentang kartu hasil Anda…' : 'Tanya jawab belum tersedia';
  updateComposer();
}

function addMessage(message, user, fallback = false) {
  const bubble = element('div', user ? 'bubble user' : 'bubble');
  if (fallback) bubble.append(element('p', 'fallback', mode === 'demo' ? 'Jawaban simulasi berdasarkan kartu contoh.' : 'Jawaban disusun dari kartu karena model sedang tidak tersedia.'));
  bubble.append(element('p', '', message));
  transcript.hidden = false;
  transcript.append(bubble);
  transcript.scrollTop = transcript.scrollHeight;
  return bubble;
}

function closeSession(message) {
  session.closed = true;
  clearTimeout(chatTimer);
  showFeedback($('chat-feedback'), message);
  refreshChat();
}

function showChatError(error) {
  if (error.status === 401) return authError();
  if (error.code === 'assessment_not_found' || ([404, 410].includes(error.status) && error.code !== 'session_not_found')) {
    clearAssessment(true);
    return navigate('hasil');
  }
  if (error.code === 'session_not_found') return closeSession(ended);
  if (error.status === 409) return closeSession(limit);
  if (error.status === 503) {
    chatUnavailable = true;
    showFeedback($('chat-feedback'), unavailable);
    return refreshConnection();
  }
  if (error.status === 429) {
    const delay = Math.ceil(Math.min(86_400, error.retryAfter || 10));
    rateLimitedUntil = Date.now() + delay * 1000;
    showFeedback($('chat-feedback'), `Terlalu banyak permintaan. Coba lagi dalam ${delay} detik.`);
    rateTimer = setTimeout(() => {
      if (!session.closed) clearFeedback($('chat-feedback'));
      refreshChat();
    }, delay * 1000);
    return;
  }
  const message = error.status === 504 ? 'Jawaban terlalu lama. Silakan coba lagi.' : error.status >= 500 ? 'Pertanyaan belum dapat diproses. Silakan coba lagi.' : error.message;
  showFeedback($('chat-feedback'), message, { error: true, requestId: error.requestId });
}

async function sendMessage(event) {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (chatInput.disabled || !message || message.length > 500) return;
  const tracking = new AbortController();
  chatRequest = tracking;
  const bubble = addMessage(message, true);
  chatInput.value = '';
  showFeedback($('chat-feedback'), 'Menyiapkan jawaban…');
  refreshChat();

  try {
    const response = await api.chat(assessment.assessment_id, { session_id: session.id, message }, tracking.signal);
    if (chatRequest !== tracking || tracking.signal.aborted) return;
    clearFeedback($('chat-feedback'));
    const ttl = meta?.chat?.session_ttl_seconds;
    if (!session.id && ttl > 0) {
      chatTimer = setTimeout(() => closeSession(ended), ttl * 1000);
    }
    session.id = response.session_id;
    session.turn = response.turn;
    if (response.answer?.trim()) addMessage(response.answer, false, response.fallback);
    else showFeedback($('chat-feedback'), 'Tidak ada jawaban untuk pertanyaan ini.');
    if (session.turn >= maxTurns()) closeSession(limit);
  } catch (error) {
    if (chatRequest !== tracking) return;
    bubble.remove();
    transcript.hidden = !transcript.childElementCount;
    chatInput.value = message;
    if (tracking.signal.aborted) showFeedback($('chat-feedback'), 'Permintaan dihentikan.');
    else showChatError(error);
  } finally {
    if (chatRequest === tracking) {
      chatRequest = null;
      refreshChat();
      if (!chatInput.disabled && view !== 'pengaturan') chatInput.focus({ preventScroll: true });
    }
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (checking || !riskReady() || assessmentRequest) return;
  clearFeedback($('assessment-error'));
  const { payload, errors } = validateAssessment(new FormData(form), schema);
  if (showFieldErrors(errors)) return;
  const tracking = new AbortController();
  assessmentRequest = tracking;
  refreshAssessment();
  try {
    const next = await api.assess(payload, tracking.signal);
    if (assessmentRequest === tracking) displayAssessment(next);
  } catch (error) {
    if (assessmentRequest === tracking && !tracking.signal.aborted) showAssessmentError(error);
  } finally {
    if (assessmentRequest === tracking) {
      assessmentRequest = null;
      refreshAssessment();
    }
  }
});

connectionForm.addEventListener('change', refreshSettings);
connectionForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const selectedMode = connectionForm.elements.mode.value;
  if (selectedMode === 'demo') return connect('demo', apiUrl, '', true);
  try {
    const url = normalizeUrl($('api-url').value);
    $('api-url').value = url;
    $('api-url').removeAttribute('aria-invalid');
    connect('pi', url, $('token').value.trim(), true);
  } catch {
    $('connection-feedback').textContent = 'Masukkan alamat HTTP(S) Raspberry Pi yang valid.';
    $('api-url').setAttribute('aria-invalid', 'true');
    $('api-url').focus();
  }
});

$('toggle-token').addEventListener('click', () => {
  const show = $('token').type === 'password';
  $('token').type = show ? 'text' : 'password';
  $('toggle-token').textContent = show ? 'Sembunyikan' : 'Tampilkan';
  $('toggle-token').setAttribute('aria-pressed', String(show));
});
$('reconnect').addEventListener('click', () => connect(mode));
$('load-case').addEventListener('click', loadExample);
$('clear-local').addEventListener('click', () => {
  resetAssessment();
  showFeedback($('clear-feedback'), 'Data sesi lokal telah dibersihkan.');
});
for (const button of document.querySelectorAll('[data-new-assessment]')) {
  button.addEventListener('click', () => {
    resetAssessment();
    navigate('penilaian');
  });
}
$('focus-chat').addEventListener('click', () => (chatInput.disabled ? $('chat-title') : chatInput).focus());
$('new-session').addEventListener('click', () => {
  clearSession();
  refreshChat();
  if (!chatInput.disabled) chatInput.focus();
});
$('stop-chat').addEventListener('click', () => chatRequest?.abort());
$('chat-form').addEventListener('submit', sendMessage);
chatInput.addEventListener('input', updateComposer);
window.addEventListener('hashchange', () => showView());

mountFields(schema);
if (mode === 'demo') loadExample();
$('app-version').textContent = APP_VERSION;
$('api-url').value = apiUrl;
connectionForm.elements.mode.value = mode;
showView(false);
connect(mode);
