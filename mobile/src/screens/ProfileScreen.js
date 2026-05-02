import React, { useState, useCallback, useContext } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet,
  Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { AuthContext } from '../context';
import { storage } from '../storage';
import { api } from '../api';
import { colors, typography, spacing, radius } from '../theme';

function InfoRow({ label, value, valueStyle }) {
  return (
    <View style={s.infoRow}>
      <Text style={s.infoLabel}>{label}</Text>
      <Text style={[s.infoValue, valueStyle]}>{value || '—'}</Text>
    </View>
  );
}

function CDLStatusPill({ expiryDate }) {
  if (!expiryDate) return <Text style={s.infoValue}>—</Text>;
  const days = Math.ceil((new Date(expiryDate) - new Date()) / 86400000);
  if (days < 0) {
    return (
      <View style={[pill.wrap, { backgroundColor: colors.errorLight }]}>
        <Text style={[pill.text, { color: colors.error }]}>EXPIRED</Text>
      </View>
    );
  }
  if (days <= 7) {
    return (
      <View style={[pill.wrap, { backgroundColor: colors.errorLight }]}>
        <Text style={[pill.text, { color: colors.error }]}>{days}d left</Text>
      </View>
    );
  }
  if (days <= 30) {
    return (
      <View style={[pill.wrap, { backgroundColor: colors.warningLight }]}>
        <Text style={[pill.text, { color: colors.warning }]}>{days}d left</Text>
      </View>
    );
  }
  return (
    <View style={[pill.wrap, { backgroundColor: colors.successLight }]}>
      <Text style={[pill.text, { color: colors.success }]}>Valid</Text>
    </View>
  );
}

export default function ProfileScreen() {
  const { auth, setAuth } = useContext(AuthContext);
  const [cdl, setCdl] = useState({});
  const [carrier, setCarrier] = useState({});
  const [phone, setPhone] = useState('');
  const [phoneValid, setPhoneValid] = useState(false);
  const [savingPhone, setSavingPhone] = useState(false);
  const [phoneSaved, setPhoneSaved] = useState(false);

  // CDL edit modal state
  const [editCDL, setEditCDL] = useState(false);
  const [cdlForm, setCdlForm] = useState({});

  useFocusEffect(
    useCallback(() => {
      storage.getCDL().then(c => {
        setCdl(c);
        setCdlForm(c);
      });
      storage.getCarrier().then(setCarrier);
      storage.getPhone().then(p => {
        if (p) {
          setPhone(p);
          setPhoneSaved(true);
          validatePhone(p);
        }
      });
    }, [])
  );

  function validatePhone(raw) {
    const digits = (raw || '').replace(/\D/g, '');
    const valid = digits.length === 10 || digits.length === 11;
    setPhoneValid(valid);
    return valid;
  }

  function formatE164(raw) {
    const digits = raw.replace(/\D/g, '');
    if (digits.length === 10) return '+1' + digits;
    if (digits.length === 11 && digits[0] === '1') return '+' + digits;
    if (raw.startsWith('+')) return raw;
    return null;
  }

  async function handleSavePhone() {
    if (!phoneValid) {
      Alert.alert('Invalid Number', 'Enter a valid 10-digit US phone number.');
      return;
    }
    const e164 = formatE164(phone);
    if (!e164) {
      Alert.alert('Invalid Number', 'Enter a valid 10-digit US phone number.');
      return;
    }
    setSavingPhone(true);
    try {
      await storage.savePhone(e164);
      api.setPhone(e164);
      setPhone(e164);
      setPhoneSaved(true);
      Alert.alert('Saved', 'Phone number saved. SMS dispatches will come to this number.');
    } catch {
      Alert.alert('Error', 'Could not save phone number.');
    } finally {
      setSavingPhone(false);
    }
  }

  async function handleSaveCDL() {
    await storage.saveCDL(cdlForm);
    setCdl(cdlForm);
    setEditCDL(false);
    Alert.alert('Saved', 'CDL information updated.');
  }

  function handleLogout() {
    Alert.alert(
      'Sign Out',
      'Are you sure you want to sign out?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out',
          style: 'destructive',
          onPress: async () => {
            await storage.clear();
            setAuth(null);
          },
        },
      ]
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Profile</Text>
        <Text style={s.headerSub}>{auth?.driverName || 'Driver'}</Text>
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* CDL Status */}
        <Text style={s.sectionTitle}>CDL Status</Text>
        <View style={s.card}>
          <InfoRow label="CDL Number" value={cdl.cdl_number} />
          <InfoRow label="Class" value={cdl.cdl_class} />
          <InfoRow label="State" value={cdl.cdl_state} />
          <InfoRow label="Expiry" value={cdl.cdl_expiry} />
          <View style={s.infoRow}>
            <Text style={s.infoLabel}>Status</Text>
            <CDLStatusPill expiryDate={cdl.cdl_expiry} />
          </View>
          <InfoRow label="Medical Card Expiry" value={cdl.medical_card_expiry} />
          <TouchableOpacity
            style={s.editBtn}
            onPress={() => { setCdlForm({ ...cdl }); setEditCDL(true); }}
            activeOpacity={0.8}
          >
            <Text style={s.editBtnText}>✏️  Edit CDL Info</Text>
          </TouchableOpacity>
        </View>

        {/* Performance */}
        <Text style={s.sectionTitle}>Performance</Text>
        <View style={s.card}>
          <InfoRow label="On-Time Rate" value={cdl.ontime_rate ? `${cdl.ontime_rate}%` : undefined} />
          <InfoRow label="Loads This Month" value={cdl.loads_month} />
          <InfoRow label="Miles This Month" value={cdl.miles_month ? Number(cdl.miles_month).toLocaleString() : undefined} />
          <InfoRow
            label="Gross This Month"
            value={cdl.gross_month ? `$${Number(cdl.gross_month).toLocaleString()}` : undefined}
            valueStyle={{ color: colors.success, fontWeight: '700' }}
          />
        </View>

        {/* Carrier Info */}
        <Text style={s.sectionTitle}>Carrier Info</Text>
        <View style={s.card}>
          <InfoRow label="Company" value={carrier.company} />
          <InfoRow label="MC #" value={carrier.mc} />
          <InfoRow label="ELD Provider" value={carrier.eld} />
        </View>

        {/* Contact & Messaging */}
        <Text style={s.sectionTitle}>Contact & Messaging</Text>
        <View style={s.card}>
          <Text style={s.fieldLabel}>My Cell Phone (for SMS dispatches)</Text>
          <TextInput
            style={[s.input, phoneValid && { borderColor: colors.success }]}
            placeholder="+1 (312) 555-0000"
            placeholderTextColor={colors.textMuted}
            value={phone}
            onChangeText={v => { setPhone(v); setPhoneSaved(false); validatePhone(v); }}
            keyboardType="phone-pad"
            returnKeyType="done"
          />
          <Text style={s.phoneHint}>
            Reply YES or NO by SMS to accept or decline load offers from dispatch.
          </Text>
          <TouchableOpacity
            style={[s.saveBtn, savingPhone && { opacity: 0.6 }]}
            onPress={handleSavePhone}
            disabled={savingPhone}
            activeOpacity={0.8}
          >
            {savingPhone ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <Text style={s.saveBtnText}>💾  Save Phone Number</Text>
            )}
          </TouchableOpacity>
          {phoneSaved && (
            <Text style={s.savedMsg}>✓ Saved — Messages tab is now active</Text>
          )}
        </View>

        {/* Account */}
        <Text style={s.sectionTitle}>Account</Text>
        <View style={s.card}>
          <InfoRow label="Driver ID" value={auth?.driverId} />
          <InfoRow label="Server URL" value={auth?.baseUrl || 'Default'} />
        </View>

        <TouchableOpacity style={s.logoutBtn} onPress={handleLogout} activeOpacity={0.8}>
          <Text style={s.logoutText}>Sign Out</Text>
        </TouchableOpacity>

        <View style={{ height: 24 }} />
      </ScrollView>

      {/* CDL Edit Inline (show/hide) */}
      {editCDL && (
        <View style={editModal.overlay}>
          <View style={editModal.sheet}>
            <Text style={editModal.title}>Edit CDL Information</Text>
            <ScrollView showsVerticalScrollIndicator={false}>
              {[
                { key: 'cdl_number', label: 'CDL Number', placeholder: 'A1234567' },
                { key: 'cdl_class', label: 'CDL Class', placeholder: 'Class A' },
                { key: 'cdl_state', label: 'State', placeholder: 'IL' },
                { key: 'cdl_expiry', label: 'CDL Expiry', placeholder: 'YYYY-MM-DD' },
                { key: 'medical_card_expiry', label: 'Medical Card Expiry', placeholder: 'YYYY-MM-DD' },
                { key: 'ontime_rate', label: 'On-Time Rate (%)', placeholder: '98' },
                { key: 'loads_month', label: 'Loads This Month', placeholder: '12' },
                { key: 'miles_month', label: 'Miles This Month', placeholder: '8500' },
                { key: 'gross_month', label: 'Gross This Month ($)', placeholder: '9200' },
              ].map(f => (
                <View key={f.key} style={editModal.field}>
                  <Text style={editModal.fieldLabel}>{f.label}</Text>
                  <TextInput
                    style={editModal.input}
                    placeholder={f.placeholder}
                    placeholderTextColor={colors.textMuted}
                    value={cdlForm[f.key] || ''}
                    onChangeText={v => setCdlForm(prev => ({ ...prev, [f.key]: v }))}
                    autoCapitalize="characters"
                    returnKeyType="next"
                  />
                </View>
              ))}
              <View style={editModal.btns}>
                <TouchableOpacity
                  style={[editModal.btn, { backgroundColor: colors.surface }]}
                  onPress={() => setEditCDL(false)}
                >
                  <Text style={[editModal.btnText, { color: colors.textSecondary }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[editModal.btn, { backgroundColor: colors.primary }]}
                  onPress={handleSaveCDL}
                >
                  <Text style={editModal.btnText}>Save</Text>
                </TouchableOpacity>
              </View>
              <View style={{ height: 40 }} />
            </ScrollView>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    backgroundColor: colors.white,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: { fontSize: typography.lg, fontWeight: '800', color: colors.textPrimary },
  headerSub: { fontSize: typography.sm, color: colors.textSecondary, fontWeight: '600' },
  scroll: { padding: spacing.md },
  sectionTitle: {
    fontSize: typography.xs,
    fontWeight: '700',
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  card: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: spacing.lg,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  infoLabel: { fontSize: typography.sm, color: colors.textSecondary },
  infoValue: { fontSize: typography.sm, fontWeight: '600', color: colors.textPrimary, maxWidth: '60%', textAlign: 'right' },
  editBtn: {
    marginTop: spacing.md,
    backgroundColor: colors.primaryLight,
    borderRadius: radius.sm,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.primary,
  },
  editBtnText: { fontSize: typography.sm, color: colors.primary, fontWeight: '700' },
  fieldLabel: {
    fontSize: typography.xs,
    fontWeight: '700',
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 6,
  },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    fontSize: typography.base,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  phoneHint: { fontSize: typography.xs, color: colors.textMuted, marginBottom: spacing.md },
  saveBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  saveBtnText: { color: colors.white, fontSize: typography.base, fontWeight: '700' },
  savedMsg: { fontSize: typography.sm, color: colors.success, marginTop: spacing.sm, textAlign: 'center', fontWeight: '600' },
  logoutBtn: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.sm,
  },
  logoutText: { fontSize: typography.base, color: colors.error, fontWeight: '700' },
});

const pill = StyleSheet.create({
  wrap: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.full },
  text: { fontSize: typography.xs, fontWeight: '700' },
});

const editModal = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
    zIndex: 100,
  },
  sheet: {
    backgroundColor: colors.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.xl,
    maxHeight: '90%',
  },
  title: { fontSize: typography.lg, fontWeight: '800', color: colors.textPrimary, marginBottom: spacing.lg },
  field: { marginBottom: spacing.sm },
  fieldLabel: {
    fontSize: typography.xs,
    fontWeight: '700',
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 4,
  },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    fontSize: typography.base,
    color: colors.textPrimary,
  },
  btns: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  btn: { flex: 1, paddingVertical: 14, borderRadius: radius.md, alignItems: 'center' },
  btnText: { fontSize: typography.base, fontWeight: '700', color: colors.white },
});
