import React, { useState, useCallback, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  RefreshControl, Modal, TextInput, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import * as Haptics from 'expo-haptics';

import { useAuth, useToast } from '../context';
import { fleetService }    from '../services/fleet';
import { telemetryService } from '../services/telemetry';
import { SkeletonCard }    from '../components/Skeleton';
import { colors, font, space, radius, shadow } from '../theme';

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusPill({ status }) {
  const MAP = {
    in_transit: { label: 'IN TRANSIT', bg: colors.primaryLight, color: colors.primary },
    dispatched:  { label: 'DISPATCHED', bg: colors.primaryLight, color: colors.primary },
    booked:      { label: 'BOOKED',     bg: colors.successLight, color: colors.success },
    delivered:   { label: 'DELIVERED',  bg: colors.successLight, color: colors.success },
    available:   { label: 'AVAILABLE',  bg: colors.surface,      color: colors.textSecondary },
  };
  const cfg = MAP[status] || { label: (status || '—').toUpperCase(), bg: colors.surface, color: colors.textSecondary };
  return (
    <View style={[pill.wrap, { backgroundColor: cfg.bg }]}>
      <View style={[pill.dot, { backgroundColor: cfg.color }]} />
      <Text style={[pill.text, { color: cfg.color }]}>{cfg.label}</Text>
    </View>
  );
}

function HOSCard({ label, value, pct, icon }) {
  const barColor = pct > 30 ? colors.successMid : pct > 10 ? colors.warningMid : colors.dangerMid;
  const valColor = pct > 30 ? colors.success    : pct > 10 ? colors.warning    : colors.danger;
  return (
    <View style={hos.card}>
      <Ionicons name={icon} size={16} color={valColor} style={{ marginBottom: 4 }} />
      <Text style={[hos.value, { color: valColor }]}>{value}</Text>
      <Text style={hos.label}>{label}</Text>
      <View style={hos.track}>
        <View style={[hos.fill, { width: `${Math.max(2, Math.min(100, pct))}%`, backgroundColor: barColor }]} />
      </View>
    </View>
  );
}

function ActionButton({ icon, label, color, bg, onPress }) {
  return (
    <TouchableOpacity style={[act.btn, { backgroundColor: bg }]} onPress={onPress} activeOpacity={0.8}>
      <View style={[act.iconCircle, { backgroundColor: color + '22' }]}>
        <Ionicons name={icon} size={22} color={color} />
      </View>
      <Text style={[act.label, { color }]}>{label}</Text>
    </TouchableOpacity>
  );
}

function SectionHeader({ title }) {
  return <Text style={s.sectionHeader}>{title}</Text>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMins(totalMins) {
  const h = Math.floor(totalMins / 60);
  const m = String(totalMins % 60).padStart(2, '0');
  return `${h}:${m}`;
}

async function getGPS() {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return null;
    const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    return { lat: loc.coords.latitude, lng: loc.coords.longitude, speed: loc.coords.speed };
  } catch { return null; }
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function HomeScreen() {
  const { auth }     = useAuth();
  const { showToast } = useToast();
  const navigation   = useNavigation();

  const [load,        setLoad]        = useState(null);
  const [hos,         setHos]         = useState(null);
  const [loadingLoad, setLoadingLoad] = useState(true);
  const [loadingHos,  setLoadingHos]  = useState(true);
  const [refreshing,  setRefreshing]  = useState(false);
  const [pickupDone,  setPickupDone]  = useState(false);
  const [issueModal,  setIssueModal]  = useState(false);
  const [issueText,   setIssueText]   = useState('');
  const [submitting,  setSubmitting]  = useState(false);

  const hosTimer = useRef(null);

  // ── Data fetch ──────────────────────────────────────────────────────────────

  const fetchLoad = useCallback(async () => {
    try {
      const l = await fleetService.getCurrentLoad(auth?.driverId || 'DRV-001');
      setLoad(l);
      if (l?.status === 'in_transit') setPickupDone(true);
    } catch { setLoad(null); }
    finally { setLoadingLoad(false); }
  }, [auth]);

  const fetchHOS = useCallback(async () => {
    try {
      const data = await telemetryService.getHOS(auth?.driverId || 'DRV-001');
      if (data?.drive_remaining != null) setHos(data);
    } catch {}
    finally { setLoadingHos(false); }
  }, [auth]);

  useFocusEffect(
    useCallback(() => {
      fetchLoad();
      fetchHOS();
      hosTimer.current = setInterval(fetchHOS, 30_000);
      return () => clearInterval(hosTimer.current);
    }, [fetchLoad, fetchHOS])
  );

  async function onRefresh() {
    setRefreshing(true);
    await Promise.all([fetchLoad(), fetchHOS()]);
    setRefreshing(false);
  }

  // ── Actions ─────────────────────────────────────────────────────────────────

  async function handlePickup() {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert('Confirm Pickup', 'Mark this load as picked up?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm Pickup', onPress: async () => {
          const pos = await getGPS();
          if (pos) {
            telemetryService.ping({ driverId: auth?.driverId, ...pos, event: 'pickup_confirmed' }).catch(() => {});
          }
          setPickupDone(true);
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showToast('Pickup confirmed — upload BOL in Docs tab.', 'success');
        },
      },
    ]);
  }

  async function handleDelivery() {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert('Confirm Delivery', 'Mark this load as delivered?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm Delivery', onPress: async () => {
          const pos = await getGPS();
          if (pos) {
            telemetryService.ping({ driverId: auth?.driverId, ...pos, event: 'delivery_confirmed' }).catch(() => {});
          }
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showToast('Delivery confirmed — upload POD now.', 'success');
          navigation.navigate('Docs');
        },
      },
    ]);
  }

  async function handleSubmitIssue() {
    if (!issueText.trim()) { showToast('Please describe the issue.', 'warning'); return; }
    setSubmitting(true);
    try {
      await telemetryService.reportIssue({ driverId: auth?.driverId, issue: issueText });
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setIssueModal(false);
      setIssueText('');
      showToast('Issue reported to dispatch.', 'success');
    } catch {
      showToast('Could not send report. Call dispatch directly.', 'error');
    } finally { setSubmitting(false); }
  }

  // ── Derived data ─────────────────────────────────────────────────────────────

  const driveMin = hos ? Math.round((hos.drive_remaining  || 0) * 60) : 659;
  const shiftMin = hos ? Math.round((hos.shift_remaining  || 0) * 60) : 765;
  const cycleMin = hos ? Math.round((hos.cycle_remaining  || 0) * 60) : 4110;

  const loadNum  = load?.load_number || load?.id?.slice(0, 8) || '—';
  const origin   = [load?.origin_city, load?.origin_state].filter(Boolean).join(', ') || '—';
  const dest     = [load?.dest_city,   load?.dest_state  ].filter(Boolean).join(', ') || '—';
  const rate     = load?.rate_total ? `$${Number(load.rate_total).toLocaleString()}` : '—';
  const miles    = load?.miles      ? Number(load.miles).toLocaleString()            : '—';
  const pickup   = load?.pickup_at  ? new Date(load.pickup_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
  const estPay   = load?.rate_total ? `$${Math.round(load.rate_total * 0.72).toLocaleString()}` : '—';

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      {/* Header ──────────────────────────────────────────────────────────── */}
      <View style={s.header}>
        <View>
          <Text style={s.headerTitle}>3 Lakes Driver</Text>
          <Text style={s.headerSub}>{auth?.driverName || 'Driver'} · {auth?.driverId || ''}</Text>
        </View>
        <View style={s.onlineRow}>
          <View style={s.onlineDot} />
          <Text style={s.onlineText}>Live</Text>
        </View>
      </View>

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Current Load ───────────────────────────────────────────────── */}
        <SectionHeader title="Current Load" />
        {loadingLoad ? (
          <SkeletonCard lines={3} />
        ) : load ? (
          <View style={[s.loadCard, shadow.sm]}>
            <View style={[s.loadAccent, { backgroundColor: load.status === 'in_transit' ? colors.primary : colors.successMid }]} />
            <View style={s.loadBody}>
              <View style={s.loadTopRow}>
                <Text style={s.loadNum}>Load #{loadNum}</Text>
                <StatusPill status={load.status} />
              </View>
              <View style={s.routeRow}>
                <View style={s.routeCity}>
                  <Text style={s.cityName}>{load?.origin_city || '—'}</Text>
                  <Text style={s.cityState}>{load?.origin_state || ''}</Text>
                </View>
                <View style={s.routeArrow}>
                  <View style={s.routeLine} />
                  <Ionicons name="arrow-forward" size={16} color={colors.textMuted} />
                </View>
                <View style={[s.routeCity, { alignItems: 'flex-end' }]}>
                  <Text style={s.cityName}>{load?.dest_city || '—'}</Text>
                  <Text style={s.cityState}>{load?.dest_state || ''}</Text>
                </View>
              </View>
              <View style={s.metaRow}>
                <View style={s.metaChip}>
                  <Ionicons name="cash-outline" size={13} color={colors.success} />
                  <Text style={[s.metaValue, { color: colors.success }]}>{rate}</Text>
                </View>
                <View style={s.metaDivider} />
                <View style={s.metaChip}>
                  <Ionicons name="navigate-outline" size={13} color={colors.textSecondary} />
                  <Text style={s.metaValue}>{miles} mi</Text>
                </View>
                <View style={s.metaDivider} />
                <View style={s.metaChip}>
                  <Ionicons name="calendar-outline" size={13} color={colors.textSecondary} />
                  <Text style={s.metaValue}>{pickup}</Text>
                </View>
              </View>
            </View>
          </View>
        ) : (
          <View style={[s.emptyCard, shadow.xs]}>
            <Ionicons name="cube-outline" size={36} color={colors.textMuted} />
            <Text style={s.emptyTitle}>No Active Load</Text>
            <Text style={s.emptyText}>Check the Loads tab to accept a new load.</Text>
            <TouchableOpacity
              style={s.emptyBtn}
              onPress={() => navigation.navigate('Loads')}
              activeOpacity={0.8}
            >
              <Text style={s.emptyBtnText}>Browse Loads</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Actions ────────────────────────────────────────────────────── */}
        <SectionHeader title="Actions" />
        <View style={s.actionGrid}>
          {!pickupDone ? (
            <ActionButton icon="checkmark-circle" label="Confirm Pickup"   color={colors.success} bg={colors.successLight}  onPress={handlePickup}   />
          ) : (
            <ActionButton icon="cube"             label="Confirm Delivery" color={colors.primary} bg={colors.primaryLight}  onPress={handleDelivery} />
          )}
          <ActionButton icon="document-attach" label="Upload Docs"     color={colors.warning}      bg={colors.warningLight}  onPress={() => navigation.navigate('Docs')}  />
          <ActionButton icon="chatbubbles"     label="Messages"        color={colors.primaryMid}   bg={colors.primaryLight}  onPress={() => navigation.navigate('Messages')} />
          <ActionButton icon="warning"         label="Report Issue"    color={colors.danger}       bg={colors.dangerLight}   onPress={() => setIssueModal(true)} />
        </View>

        {/* HOS ────────────────────────────────────────────────────────── */}
        <SectionHeader title="Hours of Service" />
        {loadingHos ? (
          <View style={s.hosRow}>
            {[0,1,2].map(i => <View key={i} style={[hos.card, { flex:1 }]}><ActivityIndicator size="small" color={colors.primary}/></View>)}
          </View>
        ) : (
          <View style={s.hosRow}>
            <HOSCard icon="car-sport"    label="Drive"     value={fmtMins(driveMin)} pct={(driveMin/660)*100}  />
            <HOSCard icon="time"         label="Shift"     value={fmtMins(shiftMin)} pct={(shiftMin/840)*100}  />
            <HOSCard icon="sync-circle"  label="70hr Cycle" value={fmtMins(cycleMin)} pct={(cycleMin/4200)*100} />
          </View>
        )}

        {/* Today's Summary ─────────────────────────────────────────── */}
        <SectionHeader title="Today's Summary" />
        <View style={s.summaryRow}>
          <View style={[s.summaryCard, shadow.xs]}>
            <Ionicons name="navigate" size={18} color={colors.primary} style={{ marginBottom: 6 }} />
            <Text style={s.summaryNum}>{miles}</Text>
            <Text style={s.summaryLabel}>Miles Driven</Text>
          </View>
          <View style={[s.summaryCard, shadow.xs]}>
            <Ionicons name="cash" size={18} color={colors.success} style={{ marginBottom: 6 }} />
            <Text style={[s.summaryNum, { color: colors.success }]}>{estPay}</Text>
            <Text style={s.summaryLabel}>Est. Pay</Text>
          </View>
        </View>

        <View style={{ height: space.xxl }} />
      </ScrollView>

      {/* Report Issue Modal ─────────────────────────────────────────── */}
      <Modal visible={issueModal} transparent animationType="slide" onRequestClose={() => setIssueModal(false)}>
        <View style={modal.overlay}>
          <TouchableOpacity style={modal.backdrop} activeOpacity={1} onPress={() => setIssueModal(false)} />
          <View style={modal.sheet}>
            <View style={modal.handle} />
            <View style={modal.headerRow}>
              <Ionicons name="warning" size={22} color={colors.danger} />
              <Text style={modal.title}>Report Issue</Text>
            </View>
            <Text style={modal.sub}>
              Describe the problem in detail. Dispatch will be notified immediately.
            </Text>
            <TextInput
              style={modal.input}
              placeholder="e.g. Flat tire on I-80 near mile marker 142, need roadside assistance…"
              placeholderTextColor={colors.textMuted}
              value={issueText}
              onChangeText={setIssueText}
              multiline
              numberOfLines={5}
              textAlignVertical="top"
              autoFocus
            />
            <View style={modal.btns}>
              <TouchableOpacity
                style={[modal.btn, modal.btnCancel]}
                onPress={() => { setIssueModal(false); setIssueText(''); }}
              >
                <Text style={modal.btnCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[modal.btn, modal.btnSubmit, submitting && { opacity: 0.6 }]}
                onPress={handleSubmitIssue}
                disabled={submitting}
              >
                {submitting
                  ? <ActivityIndicator size="small" color={colors.white} />
                  : <Text style={modal.btnSubmitText}>Send Report</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    backgroundColor: colors.card,
    paddingHorizontal: space.base, paddingVertical: space.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  headerTitle: { fontSize: font.lg, fontWeight: font.extrabold, color: colors.primary, letterSpacing: -0.3 },
  headerSub:   { fontSize: font.xs, color: colors.textSecondary, marginTop: 2 },
  onlineRow:   { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.successLight, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.full },
  onlineDot:   { width: 7, height: 7, borderRadius: radius.full, backgroundColor: colors.successMid },
  onlineText:  { fontSize: font.xs, color: colors.success, fontWeight: font.bold },
  scroll:       { flex: 1 },
  scrollContent:{ padding: space.base },
  sectionHeader:{ fontSize: font.xs, fontWeight: font.bold, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginTop: space.base, marginBottom: space.sm },

  // Load Card
  loadCard: { flexDirection: 'row', backgroundColor: colors.card, borderRadius: radius.lg, marginBottom: space.sm, overflow: 'hidden', borderWidth: 1, borderColor: colors.border },
  loadAccent: { width: 4 },
  loadBody: { flex: 1, padding: space.base },
  loadTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.md },
  loadNum: { fontSize: font.md, fontWeight: font.extrabold, color: colors.textPrimary },
  routeRow: { flexDirection: 'row', alignItems: 'center', marginBottom: space.md },
  routeCity: { flex: 1 },
  cityName: { fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary },
  cityState: { fontSize: font.xs, color: colors.textSecondary, marginTop: 2 },
  routeArrow: { paddingHorizontal: space.sm, flexDirection: 'row', alignItems: 'center', gap: 2 },
  routeLine: { width: 20, height: 1, backgroundColor: colors.border },
  metaRow: { flexDirection: 'row', alignItems: 'center' },
  metaChip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaDivider: { width: 1, height: 14, backgroundColor: colors.border, marginHorizontal: space.sm },
  metaValue: { fontSize: font.sm, fontWeight: font.semibold, color: colors.textSecondary },

  // Empty
  emptyCard: { backgroundColor: colors.card, borderRadius: radius.lg, padding: space.xl, alignItems: 'center', borderWidth: 1, borderColor: colors.border, marginBottom: space.sm },
  emptyTitle: { fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary, marginTop: space.md, marginBottom: 4 },
  emptyText: { fontSize: font.sm, color: colors.textSecondary, textAlign: 'center', marginBottom: space.base },
  emptyBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: space.lg },
  emptyBtnText: { color: colors.white, fontWeight: font.bold, fontSize: font.sm },

  // Actions
  actionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginBottom: space.sm },

  // HOS
  hosRow: { flexDirection: 'row', gap: space.sm, marginBottom: space.sm },

  // Summary
  summaryRow: { flexDirection: 'row', gap: space.sm },
  summaryCard: { flex: 1, backgroundColor: colors.card, borderRadius: radius.lg, padding: space.base, alignItems: 'center', borderWidth: 1, borderColor: colors.border },
  summaryNum: { fontSize: font.xxl, fontWeight: font.extrabold, color: colors.textPrimary, letterSpacing: -0.5 },
  summaryLabel: { fontSize: font.xs, color: colors.textMuted, marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
});

const pill = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.full, gap: 5 },
  dot:  { width: 6, height: 6, borderRadius: radius.full },
  text: { fontSize: font.xs, fontWeight: font.bold, letterSpacing: 0.4 },
});

const hos = StyleSheet.create({
  card: {
    flex: 1, backgroundColor: colors.card, borderRadius: radius.md, padding: space.md,
    alignItems: 'center', borderWidth: 1, borderColor: colors.border,
    ...shadow.xs,
  },
  value: { fontSize: font.xl, fontWeight: font.extrabold, letterSpacing: -0.5 },
  label: { fontSize: 10, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2, marginBottom: 6 },
  track: { width: '100%', height: 4, backgroundColor: colors.border, borderRadius: 2, overflow: 'hidden' },
  fill:  { height: '100%', borderRadius: 2 },
});

const act = StyleSheet.create({
  btn: {
    width: '48%', borderRadius: radius.md, padding: space.md,
    alignItems: 'center', justifyContent: 'center', gap: space.sm,
    borderWidth: 1, borderColor: colors.border,
    minHeight: 88,
  },
  iconCircle: { width: 44, height: 44, borderRadius: radius.full, alignItems: 'center', justifyContent: 'center' },
  label: { fontSize: font.xs, fontWeight: font.bold, textAlign: 'center', letterSpacing: 0.2 },
});

const modal = StyleSheet.create({
  overlay:    { flex: 1, justifyContent: 'flex-end' },
  backdrop:   { ...StyleSheet.absoluteFillObject, backgroundColor: colors.overlay },
  sheet:      { backgroundColor: colors.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: space.xl, paddingBottom: 40 },
  handle:     { width: 36, height: 4, backgroundColor: colors.border, borderRadius: 2, alignSelf: 'center', marginBottom: space.lg },
  headerRow:  { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: space.sm },
  title:      { fontSize: font.lg, fontWeight: font.extrabold, color: colors.textPrimary },
  sub:        { fontSize: font.sm, color: colors.textSecondary, marginBottom: space.base, lineHeight: 20 },
  input:      { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md, fontSize: font.base, color: colors.textPrimary, minHeight: 110, marginBottom: space.base },
  btns:       { flexDirection: 'row', gap: space.sm },
  btn:        { flex: 1, paddingVertical: 14, borderRadius: radius.md, alignItems: 'center' },
  btnCancel:  { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  btnCancelText: { fontSize: font.base, fontWeight: font.semibold, color: colors.textSecondary },
  btnSubmit:  { backgroundColor: colors.danger },
  btnSubmitText: { fontSize: font.base, fontWeight: font.bold, color: colors.white },
});
