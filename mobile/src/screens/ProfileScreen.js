import React, { useState, useCallback, useContext } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet,
  Alert, ActivityIndicator, Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { AuthContext, useToast } from '../context';
import { authService } from '../services/auth';
import { invalidateToken } from '../services/http';
import { storage } from '../storage';
import { colors, font, space, radius, shadow } from '../theme';

// ── Info row inside a card ────────────────────────────────────────────────────

function InfoRow({ icon, label, value, last }) {
  return (
    <View style={[ir.row, !last && ir.border]}>
      <Ionicons name={icon} size={16} color={colors.primary} style={ir.icon} />
      <Text style={ir.label}>{label}</Text>
      <Text style={ir.value} numberOfLines={1}>{value || '—'}</Text>
    </View>
  );
}

// ── CDL expiry pill ───────────────────────────────────────────────────────────

function ExpiryPill({ date }) {
  if (!date) return <Text style={ir.value}>—</Text>;
  const days = Math.ceil((new Date(date) - new Date()) / 86_400_000);
  const { bg, text } =
    days < 0  ? { bg: colors.dangerLight,  text: colors.danger  } :
    days <= 7  ? { bg: colors.dangerLight,  text: colors.danger  } :
    days <= 30 ? { bg: colors.warningLight, text: colors.warning } :
                 { bg: colors.successLight, text: colors.success };
  const label = days < 0 ? 'EXPIRED' : days <= 30 ? `${days}d left` : 'Valid';
  return (
    <View style={[ep.wrap, { backgroundColor: bg }]}>
      <Text style={[ep.text, { color: text }]}>{label}</Text>
    </View>
  );
}

// ── Settings row (chevron nav) ────────────────────────────────────────────────

function SettingsRow({ icon, iconBg, label, value, onPress, destructive, last }) {
  return (
    <TouchableOpacity
      style={[sr.row, !last && sr.border]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={[sr.iconWrap, { backgroundColor: iconBg || colors.primaryLight }]}>
        <Ionicons name={icon} size={17} color={destructive ? colors.danger : colors.primary} />
      </View>
      <Text style={[sr.label, destructive && { color: colors.danger }]}>{label}</Text>
      {value ? <Text style={sr.value}>{value}</Text> : null}
      <Ionicons
        name={destructive ? 'chevron-forward' : 'chevron-forward'}
        size={16}
        color={destructive ? colors.danger : colors.textMuted}
        style={sr.chevron}
      />
    </TouchableOpacity>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function ProfileScreen() {
  const { auth, setAuth } = useContext(AuthContext);
  const { showToast }     = useToast();

  const [cdl,      setCdl]      = useState({});
  const [carrier,  setCarrier]  = useState({});
  const [phone,    setPhone]    = useState('');
  const [phoneSaved, setPhoneSaved] = useState(false);
  const [phoneValid, setPhoneValid] = useState(false);
  const [savingPhone, setSavingPhone] = useState(false);

  const [cdlModal, setCdlModal] = useState(false);
  const [cdlForm,  setCdlForm]  = useState({});
  const [savingCdl, setSavingCdl] = useState(false);

  const [carrierModal, setCarrierModal] = useState(false);
  const [carrierForm,  setCarrierForm]  = useState({});

  useFocusEffect(
    useCallback(() => {
      Promise.all([storage.getCDL(), storage.getCarrier(), storage.getPhone()])
        .then(([c, car, ph]) => {
          setCdl(c); setCdlForm(c);
          setCarrier(car); setCarrierForm(car);
          if (ph) { setPhone(ph); setPhoneSaved(true); validatePhone(ph); }
        });
    }, [])
  );

  function validatePhone(raw) {
    const d = (raw || '').replace(/\D/g, '');
    const ok = d.length >= 10 && d.length <= 11;
    setPhoneValid(ok);
    return ok;
  }

  async function handleSavePhone() {
    if (!phoneValid) { showToast('Enter a valid US phone number.', 'warning'); return; }
    setSavingPhone(true);
    try {
      const d = phone.replace(/\D/g, '');
      const e164 = d.length === 10 ? `+1${d}` : `+${d}`;
      await storage.savePhone(e164);
      setPhone(e164);
      setPhoneSaved(true);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      showToast('Phone number saved.', 'success');
    } catch { showToast('Could not save phone.', 'error'); }
    finally { setSavingPhone(false); }
  }

  async function handleSaveCDL() {
    setSavingCdl(true);
    await storage.saveCDL(cdlForm);
    setCdl(cdlForm);
    setSavingCdl(false);
    setCdlModal(false);
    showToast('CDL info updated.', 'success');
  }

  async function handleSaveCarrier() {
    await storage.saveCarrier(carrierForm);
    setCarrier(carrierForm);
    setCarrierModal(false);
    showToast('Carrier info updated.', 'success');
  }

  function handleLogout() {
    Alert.alert('Sign Out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign Out', style: 'destructive',
        onPress: async () => {
          invalidateToken();
          await authService.clear();
          await storage.clear();
          setAuth(null);
        },
      },
    ]);
  }

  // Initials avatar
  const initials = (auth?.driverName || 'DR').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Driver hero ──────────────────────────────────────────────── */}
        <View style={[s.hero, shadow.sm]}>
          <View style={s.avatar}>
            <Text style={s.avatarText}>{initials}</Text>
          </View>
          <Text style={s.driverName}>{auth?.driverName || 'Driver'}</Text>
          <Text style={s.driverId}>{auth?.driverId || 'DRV-001'}</Text>

          {/* Quick stats */}
          <View style={s.statsRow}>
            <View style={s.statItem}>
              <Text style={s.statVal}>{cdl.loads_month || '—'}</Text>
              <Text style={s.statLbl}>Loads</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.statItem}>
              <Text style={s.statVal}>{cdl.miles_month ? Number(cdl.miles_month).toLocaleString() : '—'}</Text>
              <Text style={s.statLbl}>Miles</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.statItem}>
              <Text style={[s.statVal, { color: colors.successMid }]}>
                {cdl.gross_month ? `$${Number(cdl.gross_month).toLocaleString()}` : '—'}
              </Text>
              <Text style={s.statLbl}>Earned</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.statItem}>
              <Text style={s.statVal}>{cdl.ontime_rate ? `${cdl.ontime_rate}%` : '—'}</Text>
              <Text style={s.statLbl}>On-Time</Text>
            </View>
          </View>
        </View>

        {/* CDL Status ────────────────────────────────────────────────── */}
        <Text style={s.sectionTitle}>CDL Status</Text>
        <View style={[s.card, shadow.xs]}>
          <InfoRow icon="id-card"    label="CDL Number" value={cdl.cdl_number} />
          <InfoRow icon="ribbon"     label="Class"      value={cdl.cdl_class}  />
          <InfoRow icon="flag"       label="State"      value={cdl.cdl_state}  />
          <InfoRow icon="calendar"   label="Expiry"     value={cdl.cdl_expiry} />
          <View style={[ir.row, ir.border]}>
            <Ionicons name="shield-checkmark" size={16} color={colors.primary} style={ir.icon} />
            <Text style={ir.label}>Status</Text>
            <ExpiryPill date={cdl.cdl_expiry} />
          </View>
          <InfoRow icon="medical"    label="Medical Card" value={cdl.medical_card_expiry} last />
          <TouchableOpacity style={s.editCardBtn} onPress={() => setCdlModal(true)}>
            <Ionicons name="pencil" size={14} color={colors.primary} />
            <Text style={s.editCardBtnText}>Edit CDL Information</Text>
          </TouchableOpacity>
        </View>

        {/* Carrier ────────────────────────────────────────────────────── */}
        <Text style={s.sectionTitle}>Carrier</Text>
        <View style={[s.card, shadow.xs]}>
          <InfoRow icon="business" label="Company"      value={carrier.company} />
          <InfoRow icon="document" label="MC Number"    value={carrier.mc}      />
          <InfoRow icon="hardware-chip" label="ELD Provider" value={carrier.eld} last />
          <TouchableOpacity style={s.editCardBtn} onPress={() => setCarrierModal(true)}>
            <Ionicons name="pencil" size={14} color={colors.primary} />
            <Text style={s.editCardBtnText}>Edit Carrier Info</Text>
          </TouchableOpacity>
        </View>

        {/* Settings ────────────────────────────────────────────────────── */}
        <Text style={s.sectionTitle}>Settings</Text>
        <View style={[s.card, shadow.xs]}>
          {/* Phone */}
          <View style={s.phoneSection}>
            <View style={s.phoneHeader}>
              <View style={[sr.iconWrap, { backgroundColor: colors.primaryLight }]}>
                <Ionicons name="phone-portrait" size={17} color={colors.primary} />
              </View>
              <Text style={s.phoneLabel}>Cell Phone (SMS Dispatch)</Text>
            </View>
            <TextInput
              style={[s.phoneInput, phoneValid && { borderColor: colors.success }]}
              placeholder="+1 (312) 555-0000"
              placeholderTextColor={colors.textMuted}
              value={phone}
              onChangeText={v => { setPhone(v); setPhoneSaved(false); validatePhone(v); }}
              keyboardType="phone-pad"
              returnKeyType="done"
            />
            <Text style={s.phoneHint}>
              Dispatch texts load offers to this number. Reply YES/NO to accept or decline.
            </Text>
            <TouchableOpacity
              style={[s.savePhoneBtn, (!phoneValid || savingPhone) && { opacity: 0.5 }]}
              onPress={handleSavePhone}
              disabled={!phoneValid || savingPhone}
              activeOpacity={0.85}
            >
              {savingPhone
                ? <ActivityIndicator size="small" color={colors.white} />
                : <Text style={s.savePhoneBtnText}>{phoneSaved ? '✓ Phone Saved' : 'Save Phone Number'}</Text>}
            </TouchableOpacity>
          </View>
          <View style={{ height: 1, backgroundColor: colors.border, marginVertical: space.md }} />
          <SettingsRow
            icon="log-out"
            iconBg={colors.dangerLight}
            label="Sign Out"
            onPress={handleLogout}
            destructive
            last
          />
        </View>

        {/* App info */}
        <Text style={s.version}>3 Lakes Driver v2.0 · {auth?.baseUrl || 'Configured'}</Text>
        <View style={{ height: space.xxl }} />
      </ScrollView>

      {/* ── CDL Edit Modal ─────────────────────────────────────────────── */}
      <EditModal
        visible={cdlModal}
        title="Edit CDL Information"
        onClose={() => setCdlModal(false)}
        onSave={handleSaveCDL}
        saving={savingCdl}
        fields={[
          { key: 'cdl_number',        label: 'CDL Number',          placeholder: 'A1234567',    caps: 'characters' },
          { key: 'cdl_class',         label: 'CDL Class',           placeholder: 'Class A',     caps: 'words' },
          { key: 'cdl_state',         label: 'State',               placeholder: 'IL',          caps: 'characters' },
          { key: 'cdl_expiry',        label: 'CDL Expiry',          placeholder: 'YYYY-MM-DD',  caps: 'none' },
          { key: 'medical_card_expiry', label: 'Medical Card Expiry', placeholder: 'YYYY-MM-DD', caps: 'none' },
          { key: 'ontime_rate',       label: 'On-Time Rate (%)',    placeholder: '98',           keyboard: 'numeric' },
          { key: 'loads_month',       label: 'Loads This Month',    placeholder: '12',           keyboard: 'numeric' },
          { key: 'miles_month',       label: 'Miles This Month',    placeholder: '8500',         keyboard: 'numeric' },
          { key: 'gross_month',       label: 'Gross This Month ($)', placeholder: '9200',        keyboard: 'numeric' },
        ]}
        form={cdlForm}
        setForm={setCdlForm}
      />

      {/* ── Carrier Edit Modal ─────────────────────────────────────────── */}
      <EditModal
        visible={carrierModal}
        title="Edit Carrier Info"
        onClose={() => setCarrierModal(false)}
        onSave={handleSaveCarrier}
        fields={[
          { key: 'company', label: 'Company Name',  placeholder: '3 Lakes Logistics',   caps: 'words' },
          { key: 'mc',      label: 'MC Number',     placeholder: 'MC-123456',            caps: 'characters' },
          { key: 'eld',     label: 'ELD Provider',  placeholder: 'Motive / KeepTruckin', caps: 'words' },
        ]}
        form={carrierForm}
        setForm={setCarrierForm}
      />
    </SafeAreaView>
  );
}

// ── Reusable edit modal ───────────────────────────────────────────────────────

function EditModal({ visible, title, onClose, onSave, saving, fields, form, setForm }) {
  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={em.overlay}>
        <TouchableOpacity style={em.backdrop} activeOpacity={1} onPress={onClose} />
        <View style={em.sheet}>
          <View style={em.handle} />
          <Text style={em.title}>{title}</Text>
          <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
            {fields.map(f => (
              <View key={f.key} style={em.field}>
                <Text style={em.label}>{f.label}</Text>
                <TextInput
                  style={em.input}
                  placeholder={f.placeholder}
                  placeholderTextColor={colors.textMuted}
                  value={form[f.key] || ''}
                  onChangeText={v => setForm(p => ({ ...p, [f.key]: v }))}
                  autoCapitalize={f.caps || 'none'}
                  keyboardType={f.keyboard || 'default'}
                  returnKeyType="next"
                />
              </View>
            ))}
            <View style={em.btns}>
              <TouchableOpacity style={[em.btn, em.btnCancel]} onPress={onClose}>
                <Text style={em.btnCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[em.btn, em.btnSave, saving && { opacity: 0.6 }]}
                onPress={onSave}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator size="small" color={colors.white} />
                  : <Text style={em.btnSaveText}>Save Changes</Text>}
              </TouchableOpacity>
            </View>
            <View style={{ height: 40 }} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: colors.bg },
  scroll:{ padding: space.base },
  sectionTitle: { fontSize: font.xs, fontWeight: font.bold, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginTop: space.base, marginBottom: space.sm },
  card:  { backgroundColor: colors.card, borderRadius: radius.lg, marginBottom: space.sm, overflow: 'hidden', borderWidth: 1, borderColor: colors.border },

  hero:        { backgroundColor: colors.primary, borderRadius: radius.xl, padding: space.lg, alignItems: 'center', marginBottom: space.sm },
  avatar:      { width: 72, height: 72, borderRadius: radius.full, backgroundColor: 'rgba(255,255,255,0.25)', alignItems: 'center', justifyContent: 'center', marginBottom: space.md },
  avatarText:  { fontSize: font.xxl, fontWeight: font.extrabold, color: colors.white },
  driverName:  { fontSize: font.xl,  fontWeight: font.extrabold, color: colors.white, marginBottom: 3 },
  driverId:    { fontSize: font.sm,  color: 'rgba(255,255,255,0.75)', marginBottom: space.base },
  statsRow:    { flexDirection: 'row', backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: radius.md, paddingVertical: space.md, width: '100%' },
  statItem:    { flex: 1, alignItems: 'center' },
  statVal:     { fontSize: font.md, fontWeight: font.extrabold, color: colors.white },
  statLbl:     { fontSize: 10, color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: 0.4, marginTop: 2 },
  statDivider: { width: 1, backgroundColor: 'rgba(255,255,255,0.25)' },

  editCardBtn:     { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: space.base, paddingVertical: 12, borderTopWidth: 1, borderTopColor: colors.separator },
  editCardBtnText: { fontSize: font.sm, color: colors.primary, fontWeight: font.semibold },

  phoneSection: { padding: space.base },
  phoneHeader:  { flexDirection: 'row', alignItems: 'center', gap: space.md, marginBottom: space.md },
  phoneLabel:   { fontSize: font.base, fontWeight: font.semibold, color: colors.textPrimary },
  phoneInput: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12,
    fontSize: font.base, color: colors.textPrimary, marginBottom: space.sm,
  },
  phoneHint:    { fontSize: font.xs, color: colors.textMuted, marginBottom: space.md, lineHeight: 17 },
  savePhoneBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 13, alignItems: 'center' },
  savePhoneBtnText: { color: colors.white, fontSize: font.base, fontWeight: font.bold },

  version: { textAlign: 'center', fontSize: font.xs, color: colors.textMuted, marginTop: space.sm },
});

const ir = StyleSheet.create({
  row:   { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.base, paddingVertical: 13 },
  border:{ borderBottomWidth: 1, borderBottomColor: colors.separator },
  icon:  { marginRight: space.md, width: 20 },
  label: { flex: 1, fontSize: font.sm, color: colors.textSecondary },
  value: { fontSize: font.sm, fontWeight: font.semibold, color: colors.textPrimary, maxWidth: '55%', textAlign: 'right' },
});

const ep = StyleSheet.create({
  wrap: { paddingHorizontal: 9, paddingVertical: 3, borderRadius: radius.full },
  text: { fontSize: font.xs, fontWeight: font.bold },
});

const sr = StyleSheet.create({
  row:    { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.base, paddingVertical: 14 },
  border: { borderBottomWidth: 1, borderBottomColor: colors.separator },
  iconWrap: { width: 32, height: 32, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center', marginRight: space.md },
  label:  { flex: 1, fontSize: font.base, color: colors.textPrimary, fontWeight: font.medium },
  value:  { fontSize: font.sm, color: colors.textSecondary, marginRight: space.xs },
  chevron:{ marginLeft: space.xs },
});

const em = StyleSheet.create({
  overlay:  { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.overlay },
  sheet:    { backgroundColor: colors.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: space.xl, maxHeight: '92%' },
  handle:   { width: 36, height: 4, backgroundColor: colors.border, borderRadius: 2, alignSelf: 'center', marginBottom: space.lg },
  title:    { fontSize: font.lg, fontWeight: font.extrabold, color: colors.textPrimary, marginBottom: space.lg },
  field:    { marginBottom: space.md },
  label:    { fontSize: font.xs, fontWeight: font.bold, color: colors.textSecondary, textTransform: 'uppercase', letterSpacing: 0.7, marginBottom: 6 },
  input:    { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: 12, fontSize: font.base, color: colors.textPrimary },
  btns:     { flexDirection: 'row', gap: space.sm, marginTop: space.md },
  btn:      { flex: 1, paddingVertical: 14, borderRadius: radius.md, alignItems: 'center' },
  btnCancel:     { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  btnCancelText: { fontSize: font.base, fontWeight: font.semibold, color: colors.textSecondary },
  btnSave:       { backgroundColor: colors.primary },
  btnSaveText:   { fontSize: font.base, fontWeight: font.bold, color: colors.white },
});
