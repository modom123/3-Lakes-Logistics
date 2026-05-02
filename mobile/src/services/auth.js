import * as SecureStore from 'expo-secure-store';

const K = {
  TOKEN:       'auth_token',
  DRIVER_ID:   'auth_driver_id',
  DRIVER_NAME: 'auth_driver_name',
  BASE_URL:    'auth_base_url',
};

export const authService = {
  async save({ token, driverId, driverName, baseUrl }) {
    await Promise.all([
      SecureStore.setItemAsync(K.TOKEN,       token       || ''),
      SecureStore.setItemAsync(K.DRIVER_ID,   driverId    || 'DRV-001'),
      SecureStore.setItemAsync(K.DRIVER_NAME, driverName  || ''),
      SecureStore.setItemAsync(K.BASE_URL,    baseUrl     || ''),
    ]);
  },

  async load() {
    const token = await SecureStore.getItemAsync(K.TOKEN);
    if (!token) return null;
    const [driverId, driverName, baseUrl] = await Promise.all([
      SecureStore.getItemAsync(K.DRIVER_ID),
      SecureStore.getItemAsync(K.DRIVER_NAME),
      SecureStore.getItemAsync(K.BASE_URL),
    ]);
    return {
      token,
      driverId:   driverId   || 'DRV-001',
      driverName: driverName || 'Driver',
      baseUrl:    baseUrl    || '',
    };
  },

  async clear() {
    await Promise.all(Object.values(K).map(k => SecureStore.deleteItemAsync(k)));
  },
};
