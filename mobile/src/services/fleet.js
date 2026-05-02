import { http } from './http';

export const fleetService = {
  async getCurrentLoad(driverId) {
    const loads = await http.get(`/api/fleet?status=in_transit&limit=1&driver_id=${encodeURIComponent(driverId)}`);
    return Array.isArray(loads) && loads.length > 0 ? loads[0] : null;
  },

  async getAvailableLoads() {
    const loads = await http.get('/api/fleet?status=booked&limit=30');
    return Array.isArray(loads) ? loads : [];
  },

  async getLoad(id) {
    return http.get(`/api/fleet/${id}`);
  },

  async acceptLoad(id) {
    return http.patch(`/api/fleet/${id}`, { status: 'dispatched' });
  },
};
