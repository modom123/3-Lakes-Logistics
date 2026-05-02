/**
 * AsyncStorage for non-sensitive driver data.
 * Auth tokens live exclusively in SecureStore (see services/auth.js).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const K = {
  PHONE:   '3ll_phone',
  CDL:     '3ll_cdl',
  COMPANY: '3ll_company',
  MC:      '3ll_mc',
  ELD:     '3ll_eld',
};

export const storage = {
  // Phone ───────────────────────────────────────────────────────────────────

  getPhone: () => AsyncStorage.getItem(K.PHONE),

  savePhone: (phone) => AsyncStorage.setItem(K.PHONE, phone),

  // CDL ─────────────────────────────────────────────────────────────────────

  async getCDL() {
    const raw = await AsyncStorage.getItem(K.CDL);
    try { return raw ? JSON.parse(raw) : {}; }
    catch { return {}; }
  },

  saveCDL: (cdl) => AsyncStorage.setItem(K.CDL, JSON.stringify(cdl)),

  // Carrier ─────────────────────────────────────────────────────────────────

  async getCarrier() {
    const pairs = await AsyncStorage.multiGet([K.COMPANY, K.MC, K.ELD]);
    const m = Object.fromEntries(pairs.map(([k, v]) => [k, v || '']));
    return { company: m[K.COMPANY], mc: m[K.MC], eld: m[K.ELD] };
  },

  saveCarrier: ({ company, mc, eld }) =>
    AsyncStorage.multiSet([
      [K.COMPANY, company || ''],
      [K.MC,      mc      || ''],
      [K.ELD,     eld     || ''],
    ]),

  // Wipe non-sensitive data (called on logout)
  clear: () => AsyncStorage.multiRemove(Object.values(K)),
};
