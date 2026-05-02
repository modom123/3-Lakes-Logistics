import { http } from './http';

export const telemetryService = {
  async ping({ driverId, lat, lng, event, speed, heading }) {
    return http.post('/api/telemetry/ping', {
      driver_id: driverId,
      lat,
      lng,
      event,
      speed:    speed   ?? null,
      heading:  heading ?? null,
      ts:       new Date().toISOString(),
    }, { retries: 1 });
  },

  async getHOS(driverId) {
    return http.get(`/api/telemetry/hos?driver_id=${encodeURIComponent(driverId)}`);
  },

  async reportIssue({ driverId, issue }) {
    return http.post('/api/webhooks/driver_issue', {
      driver_id: driverId,
      issue:     issue.trim(),
      ts:        new Date().toISOString(),
    });
  },
};
