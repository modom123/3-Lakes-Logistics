import React, { useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  RefreshControl, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { useToast } from '../context';
import { fleetService } from '../services/fleet';
import { commsService }  from '../services/comms';
import { storage }       from '../storage';
import { SkeletonLoadRow } from '../components/Skeleton';
import { colors, font, space, radius, shadow } from '../theme';

// ── Load Row Card ─────────────────────────────────────────────────────────────

function LoadCard({ item, onAccept, onViewDetail, accepting }) {
  const origin = [item.origin_city, item.origin_state].filter(Boolean).join(', ') || 'Unknown';
  const dest   = [item.dest_city,   item.dest_state  ].filter(Boolean).join(', ') || 'Unknown';
  const rpm    = (item.rate_total && item.miles)
    ? (item.rate_total / item.miles).toFixed(2)
    : null;
  const pickup = item.pickup_at
    ? new Date(item.pickup_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : '—';
  const loadNum = item.load_number || item.id?.slice(0, 8) || '—';

  // Color-code by $/mile: >$3 = green, $2-$3 = amber, <$2 = default
  const rpmVal   = parseFloat(rpm);
  const rpmColor = !rpm ? colors.textSecondary : rpmVal >= 3 ? colors.success : rpmVal >= 2 ? colors.warning : colors.textSecondary;
  const accentBg = !rpm ? colors.border : rpmVal >= 3 ? colors.successMid : rpmVal >= 2 ? colors.warningMid : colors.border;

  return (
    <TouchableOpacity
      style={[s.card, shadow.xs]}
      onPress={() => onViewDetail(item)}
      activeOpacity={0.9}
    >
      {/* Left accent bar */}
      <View style={[s.accentBar, { backgroundColor: accentBg }]} />

      <View style={s.cardBody}>
        {/* Top row */}
        <View style={s.topRow}>
          <Text style={s.loadNum}>Load #{loadNum}</Text>
          <View style={s.distanceBadge}>
            <Ionicons name="navigate-outline" size={11} color={colors.textSecondary} />
            <Text style={s.distanceText}>
              {item.miles ? `${Number(item.miles).toLocaleString()} mi` : '—'}
            </Text>
          </View>
        </View>

        {/* Route */}
        <View style={s.routeWrap}>
          <Text style={s.routeOrigin} numberOfLines={1}>{origin}</Text>
          <Ionicons name="arrow-forward" size={14} color={colors.textMuted} style={s.routeArrow} />
          <Text style={s.routeDest} numberOfLines={1}>{dest}</Text>
        </View>

        {/* Meta row */}
        <View style={s.metaRow}>
          <Ionicons name="calendar-outline" size={12} color={colors.textMuted} />
          <Text style={s.metaText}>{pickup}</Text>
        </View>

        {/* Rate + actions */}
        <View style={s.bottomRow}>
          <View>
            <Text style={s.rate}>
              {item.rate_total ? `$${Number(item.rate_total).toLocaleString()}` : '—'}
            </Text>
            {rpm && (
              <Text style={[s.rpm, { color: rpmColor }]}>${rpm}/mi</Text>
            )}
          </View>
          <View style={s.actions}>
            {accepting === item.id ? (
              <ActivityIndicator size="small" color={colors.primary} style={{ marginRight: space.base }} />
            ) : (
              <TouchableOpacity
                style={s.acceptBtn}
                onPress={() => onAccept(item)}
                activeOpacity={0.8}
              >
                <Ionicons name="checkmark" size={14} color={colors.white} />
                <Text style={s.acceptText}>Accept</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={s.detailBtn}
              onPress={() => onViewDetail(item)}
              activeOpacity={0.8}
            >
              <Text style={s.detailText}>Details</Text>
              <Ionicons name="chevron-forward" size={14} color={colors.primary} />
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </TouchableOpacity>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function LoadsScreen() {
  const { showToast } = useToast();
  const navigation    = useNavigation();
  const [loads,     setLoads]     = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [refreshing,setRefreshing]= useState(false);
  const [accepting, setAccepting] = useState(null);

  const fetchLoads = useCallback(async () => {
    try {
      const data = await fleetService.getAvailableLoads();
      setLoads(data);
    } catch {
      setLoads([]);
      showToast('Could not load available loads.', 'error');
    } finally { setLoading(false); }
  }, [showToast]);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      fetchLoads();
    }, [fetchLoads])
  );

  async function onRefresh() {
    setRefreshing(true);
    await fetchLoads();
    setRefreshing(false);
  }

  async function handleAccept(item) {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const origin   = [item.origin_city, item.origin_state].filter(Boolean).join(', ') || '?';
    const dest     = [item.dest_city,   item.dest_state  ].filter(Boolean).join(', ') || '?';
    const rateStr  = item.rate_total ? `$${Number(item.rate_total).toLocaleString()}` : '';
    const milesStr = item.miles ? `${Number(item.miles).toLocaleString()} mi` : '';

    Alert.alert(
      'Accept This Load?',
      `${origin} → ${dest}\n${[rateStr, milesStr].filter(Boolean).join(' · ')}`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Accept Load',
          onPress: async () => {
            setAccepting(item.id);
            try {
              await fleetService.acceptLoad(item.id);
              // Notify dispatch via comms
              const phone   = await storage.getPhone();
              const loadNum = item.load_number || item.id.slice(0, 8);
              if (phone) {
                commsService.send({
                  phone,
                  body:     `YES - accepting load ${loadNum}`,
                  driverId: '',
                  loadId:   item.id,
                }).catch(() => {});
              }
              await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              showToast('Load accepted! Dispatch will confirm shortly.', 'success');
              setLoads(prev => prev.filter(l => l.id !== item.id));
              navigation.navigate('Home');
            } catch {
              showToast('Could not accept load — try again.', 'error');
            } finally { setAccepting(null); }
          },
        },
      ]
    );
  }

  function handleViewDetail(item) {
    navigation.navigate('LoadDetail', { load: item });
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <SafeAreaView style={s.safe} edges={['top']}>
        <Header count={0} onRefresh={onRefresh} />
        <View style={s.skeletonList}>
          {[0,1,2,3].map(i => <SkeletonLoadRow key={i} />)}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Header count={loads.length} onRefresh={onRefresh} />
      {loads.length === 0 ? (
        <View style={s.empty}>
          <Ionicons name="cube-outline" size={56} color={colors.border} />
          <Text style={s.emptyTitle}>No Loads Available</Text>
          <Text style={s.emptyText}>Check back soon or watch for an SMS offer from dispatch.</Text>
          <TouchableOpacity style={s.refreshBtn} onPress={onRefresh}>
            <Ionicons name="refresh" size={16} color={colors.white} />
            <Text style={s.refreshBtnText}>Refresh</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={loads}
          keyExtractor={item => item.id}
          renderItem={({ item }) => (
            <LoadCard
              item={item}
              onAccept={handleAccept}
              onViewDetail={handleViewDetail}
              accepting={accepting}
            />
          )}
          contentContainerStyle={s.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          showsVerticalScrollIndicator={false}
          ItemSeparatorComponent={() => <View style={{ height: space.sm }} />}
        />
      )}
    </SafeAreaView>
  );
}

function Header({ count, onRefresh }) {
  return (
    <View style={s.header}>
      <View>
        <Text style={s.headerTitle}>Available Loads</Text>
        {count > 0 && <Text style={s.headerCount}>{count} load{count !== 1 ? 's' : ''} available</Text>}
      </View>
      <TouchableOpacity onPress={onRefresh} style={s.headerRefresh} activeOpacity={0.7}>
        <Ionicons name="refresh" size={18} color={colors.primary} />
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    backgroundColor: colors.card, paddingHorizontal: space.base, paddingVertical: space.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  headerTitle: { fontSize: font.lg, fontWeight: font.extrabold, color: colors.textPrimary },
  headerCount: { fontSize: font.xs, color: colors.textSecondary, marginTop: 2 },
  headerRefresh: { padding: space.xs },
  skeletonList: { padding: space.base },
  list: { padding: space.base, paddingBottom: space.xxxl },

  // Card
  card: {
    backgroundColor: colors.card, borderRadius: radius.lg, flexDirection: 'row',
    overflow: 'hidden', borderWidth: 1, borderColor: colors.border,
  },
  accentBar: { width: 4 },
  cardBody:  { flex: 1, padding: space.base },
  topRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.sm },
  loadNum:   { fontSize: font.sm, fontWeight: font.bold, color: colors.textPrimary },
  distanceBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: colors.surface, paddingHorizontal: 7, paddingVertical: 3, borderRadius: radius.full },
  distanceText:  { fontSize: 11, color: colors.textSecondary, fontWeight: font.medium },

  routeWrap:   { flexDirection: 'row', alignItems: 'center', marginBottom: space.xs },
  routeOrigin: { flex: 1, fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary },
  routeArrow:  { marginHorizontal: space.xs },
  routeDest:   { flex: 1, fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary, textAlign: 'right' },

  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: space.md },
  metaText: { fontSize: font.xs, color: colors.textMuted },

  bottomRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' },
  rate: { fontSize: font.xl, fontWeight: font.extrabold, color: colors.success, letterSpacing: -0.5 },
  rpm:  { fontSize: font.xs, fontWeight: font.semibold, marginTop: 1 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  acceptBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.success, borderRadius: radius.md,
    paddingHorizontal: 14, paddingVertical: 9,
  },
  acceptText: { color: colors.white, fontSize: font.sm, fontWeight: font.bold },
  detailBtn:  { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 9 },
  detailText: { fontSize: font.sm, color: colors.primary, fontWeight: font.semibold },

  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xxl },
  emptyTitle: { fontSize: font.lg, fontWeight: font.bold, color: colors.textPrimary, marginTop: space.base, marginBottom: space.xs },
  emptyText:  { fontSize: font.sm, color: colors.textSecondary, textAlign: 'center', lineHeight: 20, marginBottom: space.lg },
  refreshBtn:  { flexDirection: 'row', alignItems: 'center', gap: space.xs, backgroundColor: colors.primary, borderRadius: radius.md, paddingHorizontal: space.lg, paddingVertical: 12 },
  refreshBtnText: { color: colors.white, fontWeight: font.bold, fontSize: font.sm },
});
