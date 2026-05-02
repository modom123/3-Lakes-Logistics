let _baseUrl = '';
let _token = '';
let _driverId = 'DRV-001';
let _phone = '';

export const api = {
  init({ baseUrl, token, driverId, phone }) {
    _baseUrl = baseUrl || '';
    _token = token || '';
    _driverId = driverId || 'DRV-001';
    _phone = phone || '';
  },

  get driverId() { return _driverId; },
  get phone() { return _phone; },

  setPhone(p) { _phone = p; },

  async request(path, method = 'GET', body = null) {
    const opts = {
      method,
      headers: {
        Authorization: `Bearer ${_token}`,
        'Content-Type': 'application/json',
      },
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(_baseUrl + path, opts);
    return res;
  },

  async json(path, method = 'GET', body = null) {
    const res = await api.request(path, method, body);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Fleet
  getCurrentLoad() {
    return api.json('/api/fleet?status=in_transit&limit=1');
  },

  getAvailableLoads() {
    return api.json('/api/fleet?status=booked&limit=30');
  },

  acceptLoad(id) {
    return api.json(`/api/fleet/${id}`, 'PATCH', { status: 'dispatched' });
  },

  // Telemetry
  pingLocation({ lat, lng, event }) {
    return api.request('/api/telemetry/ping', 'POST', {
      driver_id: _driverId,
      lat,
      lng,
      event,
      ts: new Date().toISOString(),
    });
  },

  getHOS() {
    return api.json(`/api/telemetry/hos?driver_id=${encodeURIComponent(_driverId)}`);
  },

  // Comms
  getThread() {
    if (!_phone) return Promise.resolve({ messages: [] });
    return api.json(`/api/comms/thread/${encodeURIComponent(_phone)}`);
  },

  sendMessage(body) {
    return api.request('/api/comms/send', 'POST', {
      to: _phone,
      body,
      driver_id: _driverId,
    });
  },

  markRead() {
    if (!_phone) return Promise.resolve();
    return api.request(`/api/comms/read/${encodeURIComponent(_phone)}`, 'PATCH');
  },

  replyOffer(reply, loadId) {
    return api.request('/api/comms/send', 'POST', {
      to: _phone,
      body: reply,
      driver_id: _driverId,
      load_id: loadId || undefined,
    });
  },

  // Issues
  reportIssue(issue) {
    return api.request('/api/webhooks/driver_issue', 'POST', {
      driver_id: _driverId,
      issue,
      ts: new Date().toISOString(),
    });
  },
};
