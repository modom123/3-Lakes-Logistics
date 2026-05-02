import React, { useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { useToast } from '../context';
import { fleetService } from '../services/fleet';
import { commsService }  from '../services/comms';
import { storage }       from '../storage';
import { colors, font, space, radius, shadow } from '../theme';

function DetailRow({ icon, label, value, valueStyle }) {
  if (!value) return null;
  return (
    <View style={s.detailRow}>
      <View style={s.detailIconWrap}>
        <Ionicons name={icon} size={16} color={colors.primary} />
      </View>
      <View style={s.detailContent}>
        <Text style={s.detailLabel}>{label}</Text>
        <Text style={[s.detailValue, valueStyle]}>{value}</Text>
      </View>
    </View>
  );
}

function SectionCard({ title, children }) {
  return (
    <View style={[s.card, shadow.xs]}>
      {title && <Text style={s.cardTitle}>{title}</Text>}
      {children}
    </View>
  );
}

export default function LoadDetailScreen({ route }) {
  const { load }      = route.params;
  const navigation    = useNavigation();
  const { showToast } = useToast();
  const [accepting,   setAccepting] = useState(false);

  const origin  = [load.origin_city,  load.origin_state ].filter(Boolean).join(', ') || '?';
  const dest    = [load.dest_city,    load.dest_state   ].filter(Boolean).join(', ') || '?';
  const pickup  = load.pickup_at
    ? new Date(load.pickup_at).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
    : '—';
  const rate    = load.rate_total ? `$${Number(load.rate_total).toLocaleString()}` : '—';
  const miles   = load.miles      ? `${Number(load.miles).toLocaleString()} miles` : '—';
  const rpm     = (load.rate_total && load.miles)
    ? `$${(load.rate_total / load.miles).toFixed(2)} / mile`
    : null;
  const loadNum = load.load_number || load.id?.slice(0, 8) || '—';

  async function handleAccept() {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert(
      'Accept This Load?',
      `${origin} → ${dest}\n${rate}${miles ? ` · ${miles}` : ''}`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Accept Load',
          onPress: async () => {
            setAccepting(true);
            try {
              await fleetService.acceptLoad(load.id);
              const phone = await storage.getPhone();
              if (phone) {
                commsService.send({
                  phone,
                  body:     `YES - accepting load ${loadNum}`,
                  driverId: '',
                  loadId:   load.id,
                }).catch(() => {});
              }
              await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              showToast('Load accepted! Dispatch will confirm shortly.', 'success');
              navigation.navigate('Home');
            } catch {
              showToast('Could not accept load — try again.', 'error');
            } finally { setAccepting(false); }
          },
        },
      ]
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Hero section */}
        <View style={[s.hero, shadow.sm]}>
          <View style={s.heroTop}>
            <Text style={s.loadNum}>Load #{loadNum}</Text>
            <View style={s.statusPill}>
              <View style={s.statusDot} />
              <Text style={s.statusText}>{(load.status || 'BOOKED').toUpperCase()}</Text>
            </View>
          </View>

          <View style={s.routeHero}>
            <View style={s.heroCity}>
              <Text style={s.heroCityName}>{load.origin_city || '—'}</Text>
              <Text style={s.heroCityState}>{load.origin_state || ''}</Text>
            </View>
            <View style={s.heroArrow}>
              <View style={s.heroLine} />
              <View style={[s.heroArrowCircle]}>
                <Ionicons name="arrow-forward" size={16} color={colors.white} />
              </View>
              <View style={s.heroLine} />
            </View>
            <View style={[s.heroCity, { alignItems: 'flex-end' }]}>
              <Text style={s.heroCityName}>{load.dest_city || '—'}</Text>
              <Text style={s.heroCityState}>{load.dest_state || ''}</Text>
            </View>
          </View>

          {/* Key stats */}
          <View style={s.statsRow}>
            <View style={s.statItem}>
              <Text style={s.statValue}>{rate}</Text>
              <Text style={s.statLabel}>Rate</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.statItem}>
              <Text style={s.statValue}>{load.miles ? Number(load.miles).toLocaleString() : '—'}</Text>
              <Text style={s.statLabel}>Miles</Text>
            </View>
            <View style={s.statDivider} />
            <View style={s.statItem}>
              <Text style={s.statValue}>{rpm ? `$${(load.rate_total / load.miles).toFixed(2)}` : '—'}</Text>
              <Text style={s.statLabel}>$/Mile</Text>
            </View>
          </View>
        </View>

        {/* Details */}
        <SectionCard title="Load Details">
          <DetailRow icon="calendar"           label="Pickup Date"   value={pickup} />
          <DetailRow icon="location"           label="Origin"        value={origin} />
          <DetailRow icon="flag"               label="Destination"   value={dest}   />
          <DetailRow icon="navigate"           label="Total Miles"   value={miles}  />
          <DetailRow icon="cash"               label="Total Rate"    value={rate}   valueStyle={{ color: colors.success, fontWeight: font.bold }} />
          {rpm && <DetailRow icon="trending-up" label="Rate per Mile" value={rpm}   valueStyle={{ color: colors.success }} />}
          {load.commodity && <DetailRow icon="cube"    label="Commodity"    value={load.commodity} />}
          {load.weight    && <DetailRow icon="barbell" label="Weight"       value={`${Number(load.weight).toLocaleString()} lbs`} />}
          {load.equipment && <DetailRow icon="car"     label="Equipment"    value={load.equipment} />}
          {load.notes     && <DetailRow icon="document-text" label="Notes" value={load.notes} />}
        </SectionCard>

        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Accept button pinned to bottom */}
      <View style={[s.footer, shadow.md]}>
        <TouchableOpacity
          style={[s.acceptBtn, accepting && { opacity: 0.6 }]}
          onPress={handleAccept}
          disabled={accepting}
          activeOpacity={0.85}
        >
          {accepting ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={22} color={colors.white} />
              <Text style={s.acceptText}>Accept This Load</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: space.base },

  // Hero
  hero: {
    backgroundColor: colors.primary, borderRadius: radius.xl,
    padding: space.lg, marginBottom: space.base,
  },
  heroTop:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg },
  loadNum:   { fontSize: font.md, fontWeight: font.extrabold, color: 'rgba(255,255,255,0.9)' },
  statusPill:{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: 'rgba(255,255,255,0.2)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.full },
  statusDot: { width: 6, height: 6, borderRadius: radius.full, backgroundColor: colors.white },
  statusText:{ fontSize: font.xs, fontWeight: font.bold, color: colors.white, letterSpacing: 0.4 },

  routeHero:    { flexDirection: 'row', alignItems: 'center', marginBottom: space.lg },
  heroCity:     { flex: 1 },
  heroCityName: { fontSize: font.xl, fontWeight: font.extrabold, color: colors.white, letterSpacing: -0.3 },
  heroCityState:{ fontSize: font.sm, color: 'rgba(255,255,255,0.7)', marginTop: 2 },
  heroArrow:    { paddingHorizontal: space.sm, flexDirection: 'row', alignItems: 'center', gap: 2 },
  heroLine:     { flex: 1, height: 1, backgroundColor: 'rgba(255,255,255,0.3)', width: 10 },
  heroArrowCircle: {
    width: 32, height: 32, borderRadius: radius.full,
    backgroundColor: 'rgba(255,255,255,0.25)',
    alignItems: 'center', justifyContent: 'center',
  },

  statsRow:   { flexDirection: 'row', backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: radius.md, padding: space.md },
  statItem:   { flex: 1, alignItems: 'center' },
  statValue:  { fontSize: font.lg, fontWeight: font.extrabold, color: colors.white },
  statLabel:  { fontSize: 10, color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 },
  statDivider:{ width: 1, backgroundColor: 'rgba(255,255,255,0.25)' },

  // Card
  card:      { backgroundColor: colors.card, borderRadius: radius.lg, padding: space.base, marginBottom: space.sm, borderWidth: 1, borderColor: colors.border },
  cardTitle: { fontSize: font.xs, fontWeight: font.bold, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: space.md },

  // Detail rows
  detailRow:    { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: space.sm, borderBottomWidth: 1, borderBottomColor: colors.separator },
  detailIconWrap:{ width: 32, height: 32, borderRadius: radius.sm, backgroundColor: colors.primaryLight, alignItems: 'center', justifyContent: 'center', marginRight: space.md, flexShrink: 0 },
  detailContent: { flex: 1, justifyContent: 'center' },
  detailLabel:   { fontSize: font.xs, color: colors.textMuted, marginBottom: 2 },
  detailValue:   { fontSize: font.base, fontWeight: font.semibold, color: colors.textPrimary },

  // Footer
  footer: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: colors.card, padding: space.base,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  acceptBtn: {
    backgroundColor: colors.success, borderRadius: radius.md,
    paddingVertical: 15, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: space.sm,
    ...shadow.sm,
  },
  acceptText: { color: colors.white, fontSize: font.base, fontWeight: font.extrabold, letterSpacing: 0.3 },
});
