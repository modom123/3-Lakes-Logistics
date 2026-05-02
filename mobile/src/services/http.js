import * as SecureStore from 'expo-secure-store';
import { EventEmitter } from './events';

const TIMEOUT_MS = 30_000;
const MAX_RETRIES = 3;

export class ApiError extends Error {
  constructor(message, code, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.code = code; // 'network' | 'unauthorized' | 'server' | 'client' | 'timeout'
    this.status = status;
  }
}

let _baseUrl = '';
let _token = '';
let _ready = false;

export async function initHttp({ baseUrl, token }) {
  _baseUrl = baseUrl || '';
  _token = token || '';
  _ready = true;
}

async function ensureReady() {
  if (_ready) return;
  _baseUrl = (await SecureStore.getItemAsync('auth_base_url')) || '';
  _token = (await SecureStore.getItemAsync('auth_token')) || '';
  _ready = true;
}

export function invalidateToken() {
  _token = '';
  _ready = false;
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function attempt(method, path, body, signal) {
  await ensureReady();

  const headers = {
    Authorization: `Bearer ${_token}`,
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };

  const opts = { method, headers, signal };
  if (body !== null && method !== 'GET') opts.body = JSON.stringify(body);

  const res = await fetch(_baseUrl + path, opts);

  if (res.status === 401) {
    EventEmitter.emit('auth:unauthorized');
    throw new ApiError('Session expired. Please sign in again.', 'unauthorized', 401);
  }
  if (res.status === 404) throw new ApiError('Resource not found', 'client', 404);
  if (res.status >= 500) throw new ApiError(`Server error (${res.status})`, 'server', res.status);
  if (!res.ok) throw new ApiError(`Request failed (${res.status})`, 'client', res.status);

  const text = await res.text();
  try { return text ? JSON.parse(text) : null; }
  catch { return text; }
}

export async function request(method, path, body = null, retries = MAX_RETRIES) {
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    if (i > 0) await sleep(Math.min(1000 * 2 ** (i - 1), 8000));

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
      const result = await attempt(method, path, body, controller.signal);
      clearTimeout(timer);
      return result;
    } catch (err) {
      clearTimeout(timer);

      if (err.name === 'AbortError') {
        lastErr = new ApiError('Request timed out', 'timeout');
        continue;
      }
      if (err instanceof ApiError) {
        // Don't retry on auth or client errors
        if (err.code === 'unauthorized' || err.code === 'client') throw err;
        lastErr = err;
        continue;
      }
      // TypeError = fetch/network failure
      lastErr = new ApiError(err.message || 'Network error', 'network');
    }
  }
  throw lastErr;
}

export const http = {
  get:    (path, opts)       => request('GET',    path, null, opts?.retries),
  post:   (path, body, opts) => request('POST',   path, body, opts?.retries),
  patch:  (path, body, opts) => request('PATCH',  path, body, opts?.retries),
  put:    (path, body, opts) => request('PUT',    path, body, opts?.retries),
  delete: (path, opts)       => request('DELETE', path, null, opts?.retries),
};
