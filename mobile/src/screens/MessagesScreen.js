import React, { useState, useEffect, useCallback, useRef, useContext } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, TextInput, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { api } from '../api';
import { BadgeContext } from '../context';
import { colors, typography, spacing, radius } from '../theme';

function Bubble({ msg }) {
  const isOut = msg.direction === 'outbound';
  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    : '';

  if (msg.msg_type === 'load_offer') {
    const lines = (msg.body || '').split('\n');
    const route  = lines[2] || '';
    const rate   = lines[3] || '';
    const pickup = lines[4] || '';
    return (
      <View style={b.offerWrap}>
        <View style={b.offerCard}>
          <Text style={b.offerLabel}>🚛  Load Offer</Text>
          <Text style={b.offerRoute}>{route}</Text>
          <Text style={b.offerMeta}>{[rate, pickup].filter(Boolean).join(' · ')}</Text>
          <View style={b.offerBtns}>
            <TouchableOpacity
              style={[b.offerBtn, { backgroundColor: colors.success }]}
              onPress={() => api.replyOffer('YES', msg.load_id || '').then(() => {
                Alert.alert('✅ Accepted', 'Dispatcher will confirm shortly.');
              })}
              activeOpacity={0.8}
            >
              <Text style={b.offerBtnText}>✅  Accept</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[b.offerBtn, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }]}
              onPress={() => api.replyOffer('NO', msg.load_id || '')}
              activeOpacity={0.8}
            >
              <Text style={[b.offerBtnText, { color: colors.textSecondary }]}>Decline</Text>
            </TouchableOpacity>
          </View>
        </View>
        <Text style={[b.time, { alignSelf: 'flex-start' }]}>{time}</Text>
      </View>
    );
  }

  return (
    <View style={[b.wrap, isOut ? b.wrapOut : b.wrapIn]}>
      <View style={[b.bubble, isOut ? b.bubbleOut : b.bubbleIn]}>
        <Text style={[b.bubbleText, isOut ? b.textOut : b.textIn]}>{msg.body}</Text>
      </View>
      <Text style={[b.time, isOut ? { alignSelf: 'flex-end' } : { alignSelf: 'flex-start' }]}>
        {isOut ? 'You · ' : ''}{time}
      </Text>
    </View>
  );
}

export default function MessagesScreen() {
  const { setUnread } = useContext(BadgeContext);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [hasPhone, setHasPhone] = useState(!!api.phone);
  const listRef = useRef(null);
  const pollTimer = useRef(null);
  const lastTs = useRef(null);
  const isActive = useRef(false);

  const fetchMessages = useCallback(async (scrollToEnd = false) => {
    if (!api.phone) return;
    try {
      const data = await api.getThread();
      const msgs = data?.messages || [];
      setMessages(msgs);
      if (msgs.length) lastTs.current = msgs[msgs.length - 1].created_at;
      if (scrollToEnd && listRef.current && msgs.length > 0) {
        setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
      }
    } catch {}
    finally { setLoading(false); }
  }, []);

  const markRead = useCallback(async () => {
    setUnread(0);
    api.markRead().catch(() => {});
  }, [setUnread]);

  useFocusEffect(
    useCallback(() => {
      isActive.current = true;
      setHasPhone(!!api.phone);
      if (api.phone) {
        setLoading(true);
        fetchMessages(true);
        markRead();
        pollTimer.current = setInterval(async () => {
          if (!api.phone) return;
          try {
            const data = await api.getThread();
            const msgs = data?.messages || [];
            const latest = msgs.length ? msgs[msgs.length - 1].created_at : null;
            if (latest && latest !== lastTs.current) {
              setMessages(msgs);
              lastTs.current = latest;
              if (isActive.current) {
                markRead();
                setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
              }
            }
          } catch {}
        }, 12000);
      } else {
        setLoading(false);
      }
      return () => {
        isActive.current = false;
        clearInterval(pollTimer.current);
      };
    }, [fetchMessages, markRead])
  );

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (!api.phone) {
      Alert.alert('Phone Not Set', 'Go to Profile and save your phone number first.');
      return;
    }
    setSending(true);
    setText('');
    try {
      await api.sendMessage(trimmed);
      await fetchMessages(true);
    } catch {
      Alert.alert('Error', 'Failed to send. Check your connection.');
      setText(trimmed);
    } finally {
      setSending(false);
    }
  }

  if (!hasPhone) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.header}>
          <Text style={s.headerTitle}>Messages</Text>
        </View>
        <View style={s.noPhone}>
          <Text style={s.noPhoneIcon}>📱</Text>
          <Text style={s.noPhoneTitle}>Phone Number Required</Text>
          <Text style={s.noPhoneText}>
            Go to the Profile tab and save your cell phone number to enable SMS dispatch messaging.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Messages</Text>
        <Text style={s.headerSub}>Dispatch</Text>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 80 : 0}
      >
        {loading ? (
          <View style={s.center}>
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : messages.length === 0 ? (
          <View style={s.empty}>
            <Text style={s.emptyIcon}>💬</Text>
            <Text style={s.emptyTitle}>No messages yet</Text>
            <Text style={s.emptyText}>Dispatch will reach you here and via SMS.</Text>
          </View>
        ) : (
          <FlatList
            ref={listRef}
            data={messages}
            keyExtractor={(_, i) => String(i)}
            renderItem={({ item }) => <Bubble msg={item} />}
            contentContainerStyle={s.listContent}
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
            returnKeyType="send"
            blurOnSubmit
            onSubmitEditing={handleSend}
          />
          <TouchableOpacity
            style={[s.sendBtn, (!text.trim() || sending) && s.sendBtnDisabled]}
            onPress={handleSend}
            disabled={!text.trim() || sending}
            activeOpacity={0.8}
          >
            {sending ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <Text style={s.sendIcon}>↑</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
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
  headerSub: { fontSize: typography.xs, color: colors.textSecondary },
  listContent: { padding: spacing.md, paddingBottom: spacing.sm },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: spacing.sm,
    backgroundColor: colors.white,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.sm,
  },
  input: {
    flex: 1,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 22,
    paddingHorizontal: spacing.md,
    paddingVertical: Platform.OS === 'ios' ? 10 : 8,
    fontSize: typography.base,
    color: colors.textPrimary,
    maxHeight: 100,
  },
  sendBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: { backgroundColor: colors.border },
  sendIcon: { color: colors.white, fontSize: 20, fontWeight: '700', lineHeight: 24 },
  noPhone: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  noPhoneIcon: { fontSize: 48, marginBottom: spacing.md },
  noPhoneTitle: { fontSize: typography.lg, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.xs },
  noPhoneText: { fontSize: typography.sm, color: colors.textSecondary, textAlign: 'center' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  emptyIcon: { fontSize: 48, marginBottom: spacing.md },
  emptyTitle: { fontSize: typography.lg, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.xs },
  emptyText: { fontSize: typography.sm, color: colors.textSecondary, textAlign: 'center' },
});

const b = StyleSheet.create({
  wrap: { marginBottom: spacing.sm, maxWidth: '80%' },
  wrapOut: { alignSelf: 'flex-end', alignItems: 'flex-end' },
  wrapIn: { alignSelf: 'flex-start', alignItems: 'flex-start' },
  bubble: { borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleOut: { backgroundColor: colors.primary, borderBottomRightRadius: 4 },
  bubbleIn: {
    backgroundColor: colors.white,
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: colors.border,
  },
  bubbleText: { fontSize: typography.base, lineHeight: 22 },
  textOut: { color: colors.white },
  textIn: { color: colors.textPrimary },
  time: { fontSize: 10, color: colors.textMuted, marginTop: 3, paddingHorizontal: 4 },
  offerWrap: { marginBottom: spacing.sm, maxWidth: '90%', alignSelf: 'flex-start' },
  offerCard: {
    backgroundColor: colors.white,
    borderWidth: 1.5,
    borderColor: colors.primary,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  offerLabel: { fontSize: typography.xs, color: colors.primary, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: spacing.sm },
  offerRoute: { fontSize: typography.base, fontWeight: '700', color: colors.textPrimary, marginBottom: 4 },
  offerMeta: { fontSize: typography.sm, color: colors.textSecondary, marginBottom: spacing.md },
  offerBtns: { flexDirection: 'row', gap: spacing.sm },
  offerBtn: { flex: 1, paddingVertical: 10, borderRadius: radius.sm, alignItems: 'center' },
  offerBtnText: { fontSize: typography.sm, fontWeight: '700', color: colors.white },
});
