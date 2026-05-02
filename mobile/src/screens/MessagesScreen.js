import React, { useState, useCallback, useRef, useContext, useEffect } from 'react';
import {
  View, Text, FlatList, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { BadgeContext, useToast } from '../context';
import { commsService }  from '../services/comms';
import { fleetService }  from '../services/fleet';
import { storage }       from '../storage';
import { colors, font, space, radius, shadow } from '../theme';

const POLL_MS = 12_000;

// ── Date separator ────────────────────────────────────────────────────────────

function DateLabel({ date }) {
  const label = (() => {
    const d = new Date(date);
    const today = new Date();
    const diff  = today.setHours(0,0,0,0) - d.setHours(0,0,0,0);
    if (diff === 0) return 'Today';
    if (diff === 86_400_000) return 'Yesterday';
    return new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  })();
  return (
    <View style={sep.row}>
      <View style={sep.line} />
      <Text style={sep.text}>{label}</Text>
      <View style={sep.line} />
    </View>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function Bubble({ msg, onAcceptOffer, onDeclineOffer }) {
  const isOut = msg.direction === 'outbound';
  const time  = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    : '';

  if (msg.msg_type === 'load_offer') {
    const lines   = (msg.body || '').split('\n');
    const route   = lines[2] || '';
    const rateStr = lines[3] || '';
    const dateStr = lines[4] || '';
    return (
      <View style={bbl.offerWrap}>
        <View style={[bbl.offerCard, shadow.xs]}>
          <View style={bbl.offerHeader}>
            <Ionicons name="cube" size={14} color={colors.primary} />
            <Text style={bbl.offerBadge}>Load Offer</Text>
          </View>
          {route   && <Text style={bbl.offerRoute}>{route}</Text>}
          {(rateStr || dateStr) && (
            <Text style={bbl.offerMeta}>{[rateStr, dateStr].filter(Boolean).join(' · ')}</Text>
          )}
          <View style={bbl.offerBtns}>
            <TouchableOpacity
              style={[bbl.offerBtn, { backgroundColor: colors.success }]}
              onPress={() => onAcceptOffer(msg)}
              activeOpacity={0.85}
            >
              <Ionicons name="checkmark" size={14} color={colors.white} />
              <Text style={bbl.offerBtnText}>Accept</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[bbl.offerBtn, bbl.offerBtnDecline]}
              onPress={() => onDeclineOffer(msg)}
              activeOpacity={0.85}
            >
              <Text style={[bbl.offerBtnText, { color: colors.textSecondary }]}>Decline</Text>
            </TouchableOpacity>
          </View>
        </View>
        <Text style={[bbl.time, { alignSelf: 'flex-start', marginLeft: 4 }]}>{time}</Text>
      </View>
    );
  }

  return (
    <View style={[bbl.wrap, isOut ? bbl.wrapOut : bbl.wrapIn]}>
      {!isOut && (
        <View style={bbl.avatar}>
          <Text style={bbl.avatarText}>D</Text>
        </View>
      )}
      <View style={{ maxWidth: '78%' }}>
        <View style={[bbl.bubble, isOut ? bbl.bubbleOut : bbl.bubbleIn]}>
          <Text style={[bbl.text, isOut ? bbl.textOut : bbl.textIn]}>{msg.body}</Text>
        </View>
        <Text style={[bbl.time, isOut ? { textAlign: 'right' } : {}]}>{time}</Text>
      </View>
    </View>
  );
}

// ── Grouped messages by date ──────────────────────────────────────────────────

function buildItems(messages) {
  const result = [];
  let lastDate = null;
  messages.forEach(msg => {
    const dateStr = msg.created_at
      ? new Date(msg.created_at).toDateString()
      : null;
    if (dateStr && dateStr !== lastDate) {
      result.push({ type: 'separator', date: msg.created_at, key: `sep-${msg.created_at}` });
      lastDate = dateStr;
    }
    result.push({ ...msg, type: 'message', key: msg.id || `msg-${Math.random()}` });
  });
  return result;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MessagesScreen() {
  const { setUnread }  = useContext(BadgeContext);
  const { showToast }  = useToast();

  const [messages,  setMessages]  = useState([]);
  const [phone,     setPhone]     = useState(null);
  const [text,      setText]      = useState('');
  const [loading,   setLoading]   = useState(true);
  const [sending,   setSending]   = useState(false);

  const listRef  = useRef(null);
  const lastTs   = useRef(null);
  const isActive = useRef(false);
  const pollRef  = useRef(null);

  // ── Phone resolution ────────────────────────────────────────────────────────

  useEffect(() => {
    storage.getPhone().then(p => setPhone(p || null));
  }, []);

  // ── Focus: load + start polling ─────────────────────────────────────────────

  useFocusEffect(
    useCallback(() => {
      isActive.current = true;

      async function load(scrollEnd = false) {
        if (!phone) { setLoading(false); return; }
        try {
          const msgs = await commsService.getThread(phone);
          setMessages(msgs);
          if (msgs.length) lastTs.current = msgs[msgs.length - 1].created_at;
          if (scrollEnd) setTimeout(() => listRef.current?.scrollToEnd({ animated: false }), 80);
        } catch {}
        finally { setLoading(false); }
      }

      load(true);
      markRead();
      pollRef.current = setInterval(async () => {
        if (!phone) return;
        try {
          const msgs = await commsService.getThread(phone);
          const latest = msgs.length ? msgs[msgs.length - 1].created_at : null;
          if (latest && latest !== lastTs.current) {
            setMessages(msgs);
            lastTs.current = latest;
            if (isActive.current) {
              markRead();
              setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80);
            } else {
              const newInbound = msgs.filter(m => m.direction === 'inbound' && (!lastTs.current || m.created_at > lastTs.current)).length;
              if (newInbound > 0) setUnread(n => n + newInbound);
            }
          }
        } catch {}
      }, POLL_MS);

      return () => {
        isActive.current = false;
        clearInterval(pollRef.current);
      };
    }, [phone, setUnread])   // eslint-disable-line react-hooks/exhaustive-deps
  );

  async function markRead() {
    setUnread(0);
    if (phone) commsService.markRead(phone).catch(() => {});
  }

  // ── Send ────────────────────────────────────────────────────────────────────

  async function handleSend() {
    const body = text.trim();
    if (!body)  return;
    if (!phone) { showToast('Set your phone number in Profile first.', 'warning'); return; }
    setSending(true);
    setText('');
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      await commsService.send({ phone, body, driverId: '' });
      const msgs = await commsService.getThread(phone);
      setMessages(msgs);
      if (msgs.length) lastTs.current = msgs[msgs.length - 1].created_at;
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80);
    } catch {
      showToast('Message failed — check connection.', 'error');
      setText(body);
    } finally { setSending(false); }
  }

  // ── Offer actions ───────────────────────────────────────────────────────────

  async function handleAcceptOffer(msg) {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await commsService.send({ phone, body: 'YES', driverId: '', loadId: msg.load_id });
      if (msg.load_id) {
        await fleetService.acceptLoad(msg.load_id).catch(() => {});
      }
      showToast('Load offer accepted! Dispatch will confirm.', 'success');
      const msgs = await commsService.getThread(phone);
      setMessages(msgs);
    } catch { showToast('Could not send reply.', 'error'); }
  }

  async function handleDeclineOffer(msg) {
    try {
      await commsService.send({ phone, body: 'NO', driverId: '', loadId: msg.load_id });
      showToast('Offer declined.', 'info');
      const msgs = await commsService.getThread(phone);
      setMessages(msgs);
    } catch { showToast('Could not send reply.', 'error'); }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const items = buildItems(messages);

  if (!phone) {
    return (
      <SafeAreaView style={s.safe} edges={['top']}>
        <Header />
        <View style={s.noPhone}>
          <Ionicons name="phone-portrait-outline" size={52} color={colors.border} />
          <Text style={s.noPhoneTitle}>Phone Number Required</Text>
          <Text style={s.noPhoneText}>Go to Profile and save your cell phone to activate SMS messaging with dispatch.</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Header />
      <KeyboardAvoidingView
        style={s.kav}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {loading ? (
          <View style={s.center}>
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : items.length === 0 ? (
          <View style={s.empty}>
            <Ionicons name="chatbubbles-outline" size={52} color={colors.border} />
            <Text style={s.emptyTitle}>No Messages Yet</Text>
            <Text style={s.emptyText}>Dispatch will reach you here and via SMS.</Text>
          </View>
        ) : (
          <FlatList
            ref={listRef}
            data={items}
            keyExtractor={item => item.key}
            renderItem={({ item }) =>
              item.type === 'separator'
                ? <DateLabel date={item.date} />
                : <Bubble msg={item} onAcceptOffer={handleAcceptOffer} onDeclineOffer={handleDeclineOffer} />
            }
            contentContainerStyle={s.list}
            showsVerticalScrollIndicator={false}
            onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          />
        )}

        {/* Input bar */}
        <View style={s.inputBar}>
          <TextInput
            style={s.input}
            placeholder="Message dispatch…"
            placeholderTextColor={colors.textMuted}
            value={text}
            onChangeText={setText}
            multiline
            maxLength={500}
            returnKeyType="default"
          />
          <TouchableOpacity
            style={[s.sendBtn, (!text.trim() || sending) && s.sendBtnOff]}
            onPress={handleSend}
            disabled={!text.trim() || sending}
            activeOpacity={0.8}
          >
            {sending
              ? <ActivityIndicator size="small" color={colors.white} />
              : <Ionicons name="send" size={16} color={colors.white} />}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Header() {
  return (
    <View style={s.header}>
      <View style={s.dispatchAvatar}>
        <Text style={s.dispatchAvatarText}>3L</Text>
      </View>
      <View>
        <Text style={s.headerTitle}>Dispatch</Text>
        <Text style={s.headerSub}>3 Lakes Logistics</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: colors.bg },
  kav:   { flex: 1 },
  center:{ flex: 1, justifyContent: 'center', alignItems: 'center' },
  header:{
    backgroundColor: colors.card, paddingHorizontal: space.base, paddingVertical: space.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    flexDirection: 'row', alignItems: 'center', gap: space.md,
  },
  dispatchAvatar: {
    width: 40, height: 40, borderRadius: radius.full,
    backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center',
  },
  dispatchAvatarText: { color: colors.white, fontSize: font.sm, fontWeight: font.extrabold },
  headerTitle:  { fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary },
  headerSub:    { fontSize: font.xs, color: colors.textSecondary, marginTop: 1 },
  list: { paddingHorizontal: space.base, paddingVertical: space.base },

  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end',
    padding: space.sm, gap: space.sm,
    backgroundColor: colors.card, borderTopWidth: 1, borderTopColor: colors.border,
  },
  input: {
    flex: 1, backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: 22,
    paddingHorizontal: space.md,
    paddingVertical: Platform.OS === 'ios' ? 11 : 9,
    fontSize: font.base, color: colors.textPrimary, maxHeight: 120,
  },
  sendBtn:    { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  sendBtnOff: { backgroundColor: colors.border },
  noPhone:    { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xxl },
  noPhoneTitle:{ fontSize: font.lg, fontWeight: font.bold, color: colors.textPrimary, marginTop: space.base, marginBottom: space.xs },
  noPhoneText: { fontSize: font.sm, color: colors.textSecondary, textAlign: 'center', lineHeight: 20 },
  empty:       { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xxl },
  emptyTitle:  { fontSize: font.lg, fontWeight: font.bold, color: colors.textPrimary, marginTop: space.base, marginBottom: space.xs },
  emptyText:   { fontSize: font.sm, color: colors.textSecondary, textAlign: 'center' },
});

const sep = StyleSheet.create({
  row:  { flexDirection: 'row', alignItems: 'center', marginVertical: space.md, paddingHorizontal: space.xl },
  line: { flex: 1, height: 1, backgroundColor: colors.border },
  text: { fontSize: font.xs, color: colors.textMuted, marginHorizontal: space.md, fontWeight: font.semibold },
});

const bbl = StyleSheet.create({
  wrap:   { flexDirection: 'row', marginBottom: space.md, alignItems: 'flex-end' },
  wrapOut:{ justifyContent: 'flex-end' },
  wrapIn: { justifyContent: 'flex-start' },
  avatar: { width: 28, height: 28, borderRadius: radius.full, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', marginRight: space.sm, borderWidth: 1, borderColor: colors.border },
  avatarText: { fontSize: font.xs, fontWeight: font.bold, color: colors.primary },
  bubble:    { borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleOut: { backgroundColor: colors.primary, borderBottomRightRadius: 4 },
  bubbleIn:  { backgroundColor: colors.card, borderBottomLeftRadius: 4, borderWidth: 1, borderColor: colors.border, ...shadow.xs },
  text:      { fontSize: font.base, lineHeight: 22 },
  textOut:   { color: colors.white },
  textIn:    { color: colors.textPrimary },
  time:      { fontSize: 10, color: colors.textMuted, marginTop: 4, paddingHorizontal: 4 },

  offerWrap: { marginBottom: space.base, maxWidth: '88%', alignSelf: 'flex-start' },
  offerCard: {
    backgroundColor: colors.card, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: colors.primaryBorder, padding: space.md,
  },
  offerHeader:  { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: space.sm },
  offerBadge:   { fontSize: font.xs, fontWeight: font.bold, color: colors.primary, textTransform: 'uppercase', letterSpacing: 0.6 },
  offerRoute:   { fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary, marginBottom: 3 },
  offerMeta:    { fontSize: font.sm, color: colors.textSecondary, marginBottom: space.md },
  offerBtns:    { flexDirection: 'row', gap: space.sm },
  offerBtn:     { flex: 1, paddingVertical: 10, borderRadius: radius.sm, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 5 },
  offerBtnDecline: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  offerBtnText: { fontSize: font.sm, fontWeight: font.bold, color: colors.white },
});
