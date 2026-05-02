import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  TOKEN: '3ll_token',
  DRIVER_ID: '3ll_driver_id',
  DRIVER_NAME: '3ll_driver_name',
  PHONE: '3ll_phone',
  BASE_URL: '3ll_base_url',
  CDL: '3ll_cdl',
  COMPANY: '3ll_company',
  MC: '3ll_mc',
  ELD: '3ll_eld',
};

export const storage = {
  async getAll() {
    const pairs = await AsyncStorage.multiGet(Object.values(KEYS));
    const result = {};
    pairs.forEach(([key, val]) => {
      const name = Object.keys(KEYS).find(k => KEYS[k] === key);
      if (name) result[name.toLowerCase()] = val;
    });
    // parse CDL JSON
    if (result.cdl) {
      try { result.cdl = JSON.parse(result.cdl); } catch { result.cdl = {}; }
    } else {
      result.cdl = {};
    }
    return result;
  },

  async getAuth() {
    const token = await AsyncStorage.getItem(KEYS.TOKEN);
    const driverId = await AsyncStorage.getItem(KEYS.DRIVER_ID);
    const driverName = await AsyncStorage.getItem(KEYS.DRIVER_NAME);
    const baseUrl = await AsyncStorage.getItem(KEYS.BASE_URL);
    const phone = await AsyncStorage.getItem(KEYS.PHONE);
    if (!token) return null;
    return { token, driverId: driverId || 'DRV-001', driverName, baseUrl: baseUrl || '', phone };
  },

  async saveAuth({ token, driverId, driverName, baseUrl, phone }) {
    const pairs = [
      [KEYS.TOKEN, token || ''],
      [KEYS.DRIVER_ID, driverId || 'DRV-001'],
      [KEYS.DRIVER_NAME, driverName || ''],
      [KEYS.BASE_URL, baseUrl || ''],
    ];
    if (phone) pairs.push([KEYS.PHONE, phone]);
    await AsyncStorage.multiSet(pairs);
  },

  async getPhone() {
    return AsyncStorage.getItem(KEYS.PHONE);
  },

  async savePhone(phone) {
    await AsyncStorage.setItem(KEYS.PHONE, phone);
  },

  async getCDL() {
    const raw = await AsyncStorage.getItem(KEYS.CDL);
    if (!raw) return {};
    try { return JSON.parse(raw); } catch { return {}; }
  },

  async saveCDL(cdl) {
    await AsyncStorage.setItem(KEYS.CDL, JSON.stringify(cdl));
  },

  async getCarrier() {
    const [company, mc, eld] = await AsyncStorage.multiGet([KEYS.COMPANY, KEYS.MC, KEYS.ELD]);
    return {
      company: company[1] || '',
      mc: mc[1] || '',
      eld: eld[1] || '',
    };
  },

  async saveCarrier({ company, mc, eld }) {
    await AsyncStorage.multiSet([
      [KEYS.COMPANY, company || ''],
      [KEYS.MC, mc || ''],
      [KEYS.ELD, eld || ''],
    ]);
  },

  async clear() {
    await AsyncStorage.multiRemove(Object.values(KEYS));
  },
};
