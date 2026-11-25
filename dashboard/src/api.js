export const APP_VERSION = '1.0.0';
export const DEFAULT_URL = (() => {
  try {
    if (typeof location !== 'undefined' && /^https?:$/.test(location.protocol) && location.port !== '4173') {
      return location.origin;
    }
  } catch { /* Fall back to the documented Pi address. */ }
  return 'http://192.168.50.2:8000';
})();

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'network', fields = {}, requestId = '', retryAfter = 0 } = {}) {
    super(message);
    Object.assign(this, { status, code, fields, requestId, retryAfter });
  }
}

export function normalizeUrl(value) {
  const url = new URL(value.trim());
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Gunakan alamat HTTP(S) tanpa kredensial, query, atau fragmen.');
  }
  return url.href.replace(/\/+$/, '');
}

export function createPiApi(baseUrl, token) {
  async function request(path, { body, timeout, signal, auth = true }) {
    const headers = { Accept: 'application/json' };
    if (auth) {
      headers['X-Client-Version'] = APP_VERSION;
      headers['Content-Type'] = 'application/json';
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    const deadline = AbortSignal.timeout(timeout);
    const requestSignal = signal ? AbortSignal.any([signal, deadline]) : deadline;
    try {
      const response = await fetch(`${baseUrl}/v1${path}`, {
        method: body ? 'POST' : 'GET', headers, body: body && JSON.stringify(body),
        signal: requestSignal, redirect: 'error', cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer',
      });
      const responseText = await response.text();
      let data;
      try { data = JSON.parse(responseText); } catch { /* A gateway response may lack a JSON body. */ }
      if (response.ok && data && typeof data === 'object' && !Array.isArray(data)) return data;

      const retryHeader = response.headers.get('Retry-After');
      const retrySeconds = Number(retryHeader);
      const retryAfter = Number.isFinite(retrySeconds) ? Math.max(0, retrySeconds) :
        Math.max(0, Math.ceil((Date.parse(retryHeader) - Date.now()) / 1000)) || 0;
      const error = data?.error;
      throw new ApiError(error?.message || 'Server mengembalikan respons yang tidak dapat diproses.', {
        status: response.status, code: error?.code || 'http_error', fields: error?.fields,
        requestId: data?.request_id ?? response.headers.get('X-Request-ID') ?? '', retryAfter,
      });
    } catch (error) {
      if (error instanceof ApiError || signal?.aborted) throw error;
      if (deadline.aborted) throw new ApiError('Raspberry Pi terlalu lama merespons. Silakan coba lagi.', { code: 'model_timeout', status: 504 });
      throw new ApiError('Tidak dapat terhubung ke Raspberry Pi. Periksa jaringan dan alamat IP.');
    }
  }

  return {
    health: (signal) => request('/health', { timeout: 3_000, auth: false, signal }),
    meta: (signal) => request('/meta', { timeout: 5_000, signal }),
    assess: (body, signal) => request('/assessments', { body, timeout: 15_000, signal }),
    chat: (id, body, signal) => request(`/assessments/${encodeURIComponent(id)}/chat`, { body, timeout: 180_000, signal }),
  };
}
