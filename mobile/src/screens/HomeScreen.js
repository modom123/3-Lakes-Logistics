import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  Alert, ActivityIndicator, RefreshControl, Modal, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import * as Location from 'expo-location';
import { useAuth } from '../context';
import { api } from '../api';
import { colors, typography, spacing, radius } from '../theme';

function HOSBar({ pct }) {
  const color = pct > 25 ? colors.success : pct > 10 ? colors.warning : colors.error;
  return (
    <View style={hos.track}>
      <View style={[hos.fill, { width: `${Math.max(0, Math.min(100, pct))}%`, backgroundColor: color }]} />
    </View>
  );
}

function HOSCard({ label, value, pct }) {
  const color = pct > 25 ? colors.success : pct > 10 ? colors.warning : colors.error;
  return (
    <View style={hos.card}>
      <Text style={[hos.hours, { color }]}>{value}</Text>
      <Text style={hos.label}>{label}</Text>
      <HOSBar pct={pct} />
    </View>
  );
}

function StatusPill({ status }) {
  const map = {
    in_transit: { label: 'IN TRANSIT', bg: colors.primaryLight, text: colors.primary },
    dispatched:  { label: 'DISPATCHED', bg: colors.primaryLight, text: colors.primary },
    booked:      { label: 'BOOKED', bg: colors.successLight, text: colors.success },
    delivered:   { label: 'DELIVERED', bg: colors.successLight, text: colors.success },
    available:   { label: 'AVAILABLE', bg: colors.surface, text: colors.textSecondary },
  };
  const style = map[status] || { label: (status || 'LOADING').toUpperCase(), bg: colors.surface, text: colors.textSecondary };
  return (
    <View style={[pill.wrap, { backgroundColor: style.bg }]}>
      <Text style={[pill.text, { color: style.text }]}>{style.label}</Text>
    </View>
  );
}

function fmt(minutes) {
  const h = Math.floor(minutes / 60);
  const m = String(minutes % 60).padStart(2, '0');
  return `${h}:${m}`;
}

export default function HomeScreen() {
  const { auth } = useAuth();
  const navigation = useNavigation();
  const [load, setLoad] = useState(null);
  const [hos, setHos] = useState(null);
  const [loadingLoad, setLoadingLoad] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadState, setLoadState] = useState('pre_pickup'); // pre_pickup | in_transit
  const [issueModalVisible, setIssueModalVisible] = useState(false);
  const [issueText, setIssueText] = useState('');
  const hosTimer = useRef(null);

  const fetchLoad = useCallback(async () => {
    try {
      const loads = await api.getCurrentLoad();
      if (loads && loads.length > 0) {
        setLoad(loads[0]);
        setLoadState(loads[0].status === 'in_transit' ? 'in_transit' : 'pre_pickup');
      } else {
        setLoad(null);
      }
    } catch {
      setLoad(null);
    } finally {
      setLoadingLoad(false);
    }
  }, []);

  const fetchHOS = useCallback(async () => {
    try {
      const data = await api.getHOS();
      if (data?.drive_remaining != null) setHos(data);
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchLoad();
      fetchHOS();
      hosTimer.current = setInterval(fetchHOS, 30000);
      return () => clearInterval(hosTimer.current);
    }, [fetchLoad, fetchHOS])
  );

  async function onRefresh() {
    setRefreshing(true);
    await Promise.all([fetchLoad(), fetchHOS()]);
    setRefreshing(false);
  }

  async function getGPS() {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return null;
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      return { lat: loc.coords.latitude, lng: loc.coords.longitude };
    } catch { return null; }
  }

  async function confirmPickup() {
    Alert.alert('Confirm Pickup', 'Mark this load as picked up?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm', onPress: async () => {
          const pos = await getGPS();
          if (pos) {
            api.pingLocation({ ...pos, event: 'pickup_confirmed' }).catch(() => {});
          }
          setLoadState('in_transit');
          Alert.alert('Pickup Confirmed', 'Great! Now upload your BOL in the Docs tab.', [
            { text: 'Go to Docs', onPress: () => navigation.navigate('Docs') },
            { text: 'OK' },
          ]);
        },
      },
    ]);
  }

  async function confirmDelivery() {
    Alert.alert('Confirm Delivery', 'Mark this load as delivered?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm', onPress: async () => {
          const pos = await getGPS();
          if (pos) {
            api.pingLocation({ ...pos, event: 'delivery_confirmed' }).catch(() => {});
          }
          navigation.navigate('Docs');
          Alert.alert('Delivery Confirmed', 'Please upload your POD now.');
        },
      },
    ]);
  }

  async function submitIssue() {
    if (!issueText.trim()) {
      Alert.alert('Required', 'Please describe the issue.');
      return;
    }
    try {
      await api.reportIssue(issueText.trim());
      setIssueModalVisible(false);
      setIssueText('');
      Alert.alert('Reported', 'Your issue has been sent to dispatch.');
    } catch {
      Alert.alert('Error', 'Could not send report. Please call dispatch directly.');
    }
  }

  // HOS data
  const driveMin  = hos ? Math.round((hos.drive_remaining  || 0) * 60) : 659;
  const shiftMin  = hos ? Math.round((hos.shift_remaining  || 0) * 60) : 765;
  const cycleMin  = hos ? Math.round((hos.cycle_remaining  || 0) * 60) : 4110;
  const drivePct  = (driveMin / 660)  * 100;
  const shiftPct  = (shiftMin / 840)  * 100;
  const cyclePct  = (cycleMin / 4200) * 100;

  const pickupDate = load?.pickup_at
    ? new Date(load.pickup_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : '—';
  const rate = load?.rate_total ? `$${Number(load.rate_total).toLocaleString()}` : '—';
  const miles = load?.miles ? load.miles.toLocaleString() : '—';
  const estPay = load?.rate_total ? `$${Math.round(load.rate_total * 0.72).toLocaleString()}` : '—';

  return (
    <SafeAreaView style={s.safe}>
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.headerTitle}>3 Lakes Driver</Text>
          <Text style={s.headerSub}>{auth?.driverName || 'Driver'}</Text>
        </View>
        <View style={s.onlineRow}>
          <View style={s.onlineDot} />
          <Text style={s.onlineLabel}>Online</Text>
        </View>
      </View>

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Current Load */}
        <Text style={s.sectionTitle}>Current Load</Text>
        <View style={s.card}>
          {loadingLoad ? (
            <ActivityIndicator color={colors.primary} />
          ) : load ? (
            <>
              <View style={s.loadHeader}>
                <Text style={s.loadNumber}>{load.load_number || load.id?.slice(0, 8) || 'LOAD-001'}</Text>
                <StatusPill status={load.status} />
              </View>
              <View style={s.route}>
                <View style={s.city}>
                  <Text style={s.cityName}>{load.origin_city || '—'}</Text>
                  <Text style={s.cityState}>{load.origin_state || ''}</Text>
                </View>
                <Text style={s.arrow}>→</Text>
                <View style={[s.city, { alignItems: 'flex-end' }]}>
                  <Text style={s.cityName}>{load.dest_city || '—'}</Text>
                  <Text style={s.cityState}>{load.dest_state || ''}</Text>
                </View>
              </View>
              <View style={s.metaRow}>
                <View style={s.metaItem}>
                  <Text style={s.metaLabel}>Rate</Text>
                  <Text style={s.metaValue}>{rate}</Text>
                </View>
                <View style={s.metaItem}>
                  <Text style={s.metaLabel}>Miles</Text>
                  <Text style={s.metaValue}>{miles}</Text>
                </View>
                <View style={s.metaItem}>
                  <Text style={s.metaLabel}>Pickup</Text>
                  <Text style={s.metaValue}>{pickupDate}</Text>
                </View>
              </View>
            </>
          ) : (
            <View style={s.emptyLoad}>
              <Text style={s.emptyIcon}>🚛</Text>
              <Text style={s.emptyText}>No active load. Check the Loads tab.</Text>
            </View>
          )}
        </View>

        {/* Actions */}
        <Text style={s.sectionTitle}>Actions</Text>
        {loadState === 'pre_pickup' ? (
          <TouchableOpacity style={[s.btn, s.btnSuccess]} onPress={confirmPickup} activeOpacity={0.8}>
            <Text style={s.btnText}>✅  Confirm Pickup</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[s.btn, s.btnPrimary]} onPress={confirmDelivery} activeOpacity={0.8}>
            <Text style={s.btnText}>📦  Confirm Delivery</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={[s.btn, s.btnWarning]} onPress={() => navigation.navigate('Docs')} activeOpacity={0.8}>
          <Text style={[s.btnText, { color: colors.textPrimary }]}>📎  Upload BOL / POD</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.btn, s.btnGhost]} onPress={() => setIssueModalVisible(true)} activeOpacity={0.8}>
          <Text style={[s.btnText, { color: colors.textPrimary }]}>⚠️  Report Issue / Breakdown</Text>
        </TouchableOpacity>

        {/* HOS */}
        <Text style={s.sectionTitle}>HOS — Hours of Service</Text>
        <View style={hosStyles.row}>
          <HOSCard label="Drive" value={fmt(driveMin)} pct={drivePct} />
          <HOSCard label="Shift" value={fmt(shiftMin)} pct={shiftPct} />
          <HOSCard label="70hr Cycle" value={fmt(cycleMin)} pct={cyclePct} />
        </View>

        {/* Today's Summary */}
        <Text style={s.sectionTitle}>Today's Summary</Text>
        <View style={s.summaryRow}>
          <View style={[s.card, { flex: 1, marginRight: 6 }]}>
            <Text style={s.summaryLabel}>Miles Today</Text>
            <Text style={s.summaryValue}>{miles}</Text>
          </View>
          <View style={[s.card, { flex: 1, marginLeft: 6 }]}>
            <Text style={s.summaryLabel}>Est. Pay</Text>
            <Text style={[s.summaryValue, { color: colors.success }]}>{estPay}</Text>
          </View>
        </View>

        <View style={{ height: 20 }} />
      </ScrollView>

      {/* Report Issue Modal */}
      <Modal visible={issueModalVisible} transparent animationType="slide">
        <View style={modal.overlay}>
          <View style={modal.sheet}>
            <Text style={modal.title}>Report Issue / Breakdown</Text>
            <Text style={modal.sub}>Describe the problem. Dispatch will be notified immediately.</Text>
            <TextInput
              style={modal.input}
              placeholder="e.g. Flat tire on I-80 near mile marker 142..."
              placeholderTextColor={colors.textMuted}
              value={issueText}
              onChangeText={setIssueText}
              multiline
              numberOfLines={4}
              textAlignVertical="top"
              autoFocus
            />
            <View style={modal.btns}>
              <TouchableOpacity
                style={[modal.btn, { backgroundColor: colors.surface }]}
                onPress={() => { setIssueModalVisible(false); setIssueText(''); }}
              >
                <Text style={[modal.btnText, { color: colors.textSecondary }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[modal.btn, { backgroundColor: colors.error }]} onPress={submitIssue}>
                <Text style={modal.btnText}>Send Report</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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
  headerTitle: { fontSize: typography.lg, fontWeight: '800', color: colors.primary },
  headerSub: { fontSize: typography.xs, color: colors.textSecondary, marginTop: 1 },
  onlineRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  onlineDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  onlineLabel: { fontSize: typography.xs, color: colors.textSecondary },
  scroll: { flex: 1 },
  scrollContent: { padding: spacing.md },
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
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    borderWidth: 1,
    borderColor: colors.border,
  },
  loadHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md },
  loadNumber: { fontSize: typography.lg, fontWeight: '700', color: colors.textPrimary },
  route: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md },
  city: { flex: 1 },
  cityName: { fontSize: typography.base, fontWeight: '700', color: colors.textPrimary },
  cityState: { fontSize: typography.xs, color: colors.textSecondary, marginTop: 2 },
  arrow: { fontSize: 18, color: colors.textMuted, marginHorizontal: spacing.sm },
  metaRow: { flexDirection: 'row', gap: spacing.sm },
  metaItem: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    padding: spacing.sm,
  },
  metaLabel: { fontSize: 10, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 },
  metaValue: { fontSize: typography.base, fontWeight: '700', color: colors.textPrimary },
  emptyLoad: { alignItems: 'center', paddingVertical: spacing.lg },
  emptyIcon: { fontSize: 36, marginBottom: spacing.sm },
  emptyText: { fontSize: typography.sm, color: colors.textSecondary, textAlign: 'center' },
  btn: {
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: spacing.sm,
    flexDirection: 'row',
    justifyContent: 'center',
  },
  btnSuccess: { backgroundColor: colors.success },
  btnPrimary: { backgroundColor: colors.primary },
  btnWarning: { backgroundColor: '#FEF3C7', borderWidth: 1, borderColor: '#FDE68A' },
  btnGhost: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border },
  btnText: { fontSize: typography.base, fontWeight: '700', color: colors.white },
  summaryRow: { flexDirection: 'row', marginBottom: spacing.sm },
  summaryLabel: { fontSize: typography.xs, color: colors.textSecondary, fontWeight: '600', marginBottom: 4 },
  summaryValue: { fontSize: typography.xxxl, fontWeight: '800', color: colors.textPrimary },
});

const hosStyles = StyleSheet.create({
  row: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  card: {
    flex: 1,
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  hours: { fontSize: typography.xl, fontWeight: '800' },
  label: { fontSize: 10, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 },
  track: { height: 4, width: '100%', backgroundColor: colors.border, borderRadius: 2, marginTop: 6, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 2 },
});

const hos = hosStyles;

const pill = StyleSheet.create({
  wrap: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.full },
  text: { fontSize: typography.xs, fontWeight: '700' },
});

const modal = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.xl,
    paddingBottom: 40,
  },
  title: { fontSize: typography.lg, fontWeight: '800', color: colors.textPrimary, marginBottom: 4 },
  sub: { fontSize: typography.sm, color: colors.textSecondary, marginBottom: spacing.md },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: typography.base,
    color: colors.textPrimary,
    minHeight: 100,
    marginBottom: spacing.md,
  },
  btns: { flexDirection: 'row', gap: spacing.sm },
  btn: { flex: 1, paddingVertical: 14, borderRadius: radius.md, alignItems: 'center' },
  btnText: { fontSize: typography.base, fontWeight: '700', color: colors.white },
});
