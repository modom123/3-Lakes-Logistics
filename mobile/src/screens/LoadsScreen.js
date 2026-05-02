import React, { useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  Alert, ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { api } from '../api';
import { colors, typography, spacing, radius } from '../theme';

function LoadRow({ item, onAccept, onPass }) {
  const origin = [item.origin_city, item.origin_state].filter(Boolean).join(', ') || '?';
  const dest   = [item.dest_city, item.dest_state].filter(Boolean).join(', ') || '?';
  const rpm    = (item.rate_total && item.miles)
    ? `$${(item.rate_total / item.miles).toFixed(2)}/mi`
    : null;
  const pickup = item.pickup_at
    ? new Date(item.pickup_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : '—';
  const loadNum = item.load_number || item.id?.slice(0, 8) || '—';

  return (
    <View style={s.row}>
      <View style={s.rowLeft}>
        <View style={s.routeWrap}>
          <Text style={s.originText}>{origin}</Text>
          <Text style={s.arrowText}>→</Text>
          <Text style={s.destText}>{dest}</Text>
        </View>
        <Text style={s.rowMeta}>
          {loadNum}{item.miles ? ` · ${Number(item.miles).toLocaleString()} mi` : ''}  ·  {pickup}
        </Text>
        <View style={s.rateRow}>
          <Text style={s.rate}>
            {item.rate_total ? `$${Number(item.rate_total).toLocaleString()}` : '—'}
          </Text>
          {rpm && <Text style={s.rpm}>{rpm}</Text>}
        </View>
      </View>
      <View style={s.rowActions}>
        <TouchableOpacity style={s.acceptBtn} onPress={() => onAccept(item)} activeOpacity={0.8}>
          <Text style={s.acceptText}>Accept</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.passBtn} onPress={() => onPass(item)} activeOpacity={0.8}>
          <Text style={s.passText}>Pass</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

export default function LoadsScreen() {
  const navigation = useNavigation();
  const [loads, setLoads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [accepting, setAccepting] = useState(null);

  const fetchLoads = useCallback(async () => {
    try {
      const data = await api.getAvailableLoads();
      setLoads(Array.isArray(data) ? data : []);
    } catch {
      setLoads([]);
    } finally {
      setLoading(false);
    }
  }, []);

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
    Alert.alert(
      'Accept Load',
      `Accept load from ${item.origin_city || '?'} → ${item.dest_city || '?'}?\n\n${
        item.rate_total ? `$${Number(item.rate_total).toLocaleString()}` : ''
      }${item.miles ? ` · ${Number(item.miles).toLocaleString()} mi` : ''}`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Accept',
          onPress: async () => {
            setAccepting(item.id);
            try {
              await api.acceptLoad(item.id);
              // send SMS confirmation if phone configured
              const loadNum = item.load_number || item.id.slice(0, 8);
              if (api.phone) {
                api.replyOffer(`YES - accepting load ${loadNum}`, item.id).catch(() => {});
              }
              Alert.alert(
                '✅ Load Accepted',
                'Dispatch will confirm details shortly. Check the Home tab for your load.',
                [{ text: 'Go to Home', onPress: () => navigation.navigate('Home') }, { text: 'OK' }]
              );
              fetchLoads();
            } catch {
              Alert.alert('Error', 'Could not accept load. Please try again or contact dispatch.');
            } finally {
              setAccepting(null);
            }
          },
        },
      ]
    );
  }

  function handlePass(item) {
    Alert.alert('Passed', 'Load skipped.', [{ text: 'OK' }]);
    setLoads(prev => prev.filter(l => l.id !== item.id));
  }

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.header}>
          <Text style={s.headerTitle}>Available Loads</Text>
        </View>
        <View style={s.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>Available Loads</Text>
        <TouchableOpacity onPress={onRefresh} activeOpacity={0.7}>
          <Text style={s.refreshBtn}>↻ Refresh</Text>
        </TouchableOpacity>
      </View>

      <Text style={s.hint}>
        Accept a load — dispatch confirms and sends details via SMS.
      </Text>

      {loads.length === 0 ? (
        <View style={s.empty}>
          <Text style={s.emptyIcon}>🚛</Text>
          <Text style={s.emptyTitle}>No loads right now</Text>
          <Text style={s.emptyText}>Check back soon or watch for an SMS offer from dispatch.</Text>
          <TouchableOpacity style={s.emptyBtn} onPress={onRefresh}>
            <Text style={s.emptyBtnText}>Refresh</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={loads}
          keyExtractor={item => item.id}
          renderItem={({ item }) => (
            <View style={accepting === item.id ? { opacity: 0.5 } : {}}>
              <LoadRow
                item={item}
                onAccept={handleAccept}
                onPass={handlePass}
              />
            </View>
          )}
          contentContainerStyle={s.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
          }
          ItemSeparatorComponent={() => <View style={s.separator} />}
          showsVerticalScrollIndicator={false}
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
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
  refreshBtn: { fontSize: typography.sm, color: colors.primary, fontWeight: '600' },
  hint: {
    fontSize: typography.xs,
    color: colors.textSecondary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  list: { padding: spacing.md },
  separator: { height: spacing.sm },
  row: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  rowLeft: { flex: 1, paddingRight: spacing.sm },
  routeWrap: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', marginBottom: 4 },
  originText: { fontSize: typography.sm, fontWeight: '700', color: colors.textPrimary },
  arrowText: { fontSize: typography.sm, color: colors.textMuted, marginHorizontal: 4 },
  destText: { fontSize: typography.sm, fontWeight: '700', color: colors.textPrimary },
  rowMeta: { fontSize: typography.xs, color: colors.textSecondary, marginBottom: 4 },
  rateRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  rate: { fontSize: typography.lg, fontWeight: '800', color: colors.success },
  rpm: { fontSize: typography.xs, color: colors.textSecondary },
  rowActions: { gap: spacing.xs },
  acceptBtn: {
    backgroundColor: colors.success,
    borderRadius: radius.sm,
    paddingVertical: 8,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  acceptText: { color: colors.white, fontSize: typography.xs, fontWeight: '700' },
  passBtn: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingVertical: 8,
    paddingHorizontal: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  passText: { color: colors.textSecondary, fontSize: typography.xs, fontWeight: '600' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  emptyIcon: { fontSize: 48, marginBottom: spacing.md },
  emptyTitle: { fontSize: typography.lg, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.xs },
  emptyText: { fontSize: typography.sm, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.lg },
  emptyBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: 12,
    paddingHorizontal: spacing.xl,
  },
  emptyBtnText: { color: colors.white, fontWeight: '700', fontSize: typography.base },
});
