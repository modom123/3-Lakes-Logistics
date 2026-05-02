import { http } from './http';

export const commsService = {
  async getThread(phone) {
    if (!phone) return [];
    const data = await http.get(`/api/comms/thread/${encodeURIComponent(phone)}`);
    return data?.messages || [];
  },

  async send({ phone, body, driverId, loadId }) {
    return http.post('/api/comms/send', {
      to:        phone,
      body:      body.trim(),
      driver_id: driverId,
      ...(loadId ? { load_id: loadId } : {}),
    });
  },

  async markRead(phone) {
    if (!phone) return;
    return http.patch(`/api/comms/read/${encodeURIComponent(phone)}`);
  },
};
