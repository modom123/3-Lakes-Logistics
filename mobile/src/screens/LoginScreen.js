import React, { useState, useContext, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { AuthContext, useToast } from '../context';
import { authService } from '../services/auth';
import { initHttp } from '../services/http';
import { storage } from '../storage';
import { colors, font, space, radius, shadow } from '../theme';

function Field({ label, icon, children }) {
  return (
    <View style={s.field}>
      <Text style={s.label}>{label}</Text>
      <View style={s.inputRow}>
        <Ionicons name={icon} size={18} color={colors.textMuted} style={s.inputIcon} />
        {children}
      </View>
    </View>
  );
}

export default function LoginScreen() {
  const { setAuth } = useContext(AuthContext);
  const { showToast } = useToast();
  const [form, setForm] = useState({
    driverName: '',
    driverId:   '',
    token:      '',
    baseUrl:    '',
    phone:      '',
  });
  const [showToken, setShowToken] = useState(false);
  const [loading,   setLoading]   = useState(false);

  const refs = {
    driverId: useRef(null),
    token:    useRef(null),
    baseUrl:  useRef(null),
    phone:    useRef(null),
  };

  function set(key, val) { setForm(p => ({ ...p, [key]: val })); }

  function validate() {
    if (!form.driverName.trim())
      return 'Please enter your name.';
    if (!form.token.trim())
      return 'Please enter the API token provided by dispatch.';
    if (form.phone.trim()) {
      const digits = form.phone.replace(/\D/g, '');
      if (digits.length < 10 || digits.length > 11)
        return 'Enter a valid 10-digit US phone number.';
    }
    return null;
  }

  async function handleLogin() {
    const err = validate();
    if (err) { Alert.alert('Required', err); return; }

    setLoading(true);
    try {
      const auth = {
        token:      form.token.trim(),
        driverId:   form.driverId.trim()  || 'DRV-001',
        driverName: form.driverName.trim(),
        baseUrl:    form.baseUrl.trim().replace(/\/+$/, ''),
      };

      await authService.save(auth);
      initHttp({ baseUrl: auth.baseUrl, token: auth.token });

      if (form.phone.trim()) {
        const digits = form.phone.replace(/\D/g, '');
        const e164 = digits.length === 10 ? `+1${digits}` : `+${digits}`;
        await storage.savePhone(e164);
      }

      setAuth(auth);
    } catch {
      showToast('Could not save credentials — please try again.', 'error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView
        style={s.kav}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Logo ─────────────────────────────────────────────────────── */}
          <View style={s.logoArea}>
            <View style={s.logoMark}>
              <Ionicons name="cube" size={34} color={colors.white} />
            </View>
            <Text style={s.logoTitle}>3 Lakes Driver</Text>
            <Text style={s.logoSub}>Carrier Operations App</Text>
          </View>

          {/* Card ─────────────────────────────────────────────────────── */}
          <View style={[s.card, shadow.md]}>
            <Text style={s.cardTitle}>Sign In</Text>
            <Text style={s.cardSub}>
              Enter the credentials given to you by dispatch.
            </Text>

            <Field label="Your Full Name *" icon="person-outline">
              <TextInput
                style={s.input}
                placeholder="John Smith"
                placeholderTextColor={colors.textMuted}
                value={form.driverName}
                onChangeText={v => set('driverName', v)}
                autoCapitalize="words"
                returnKeyType="next"
                onSubmitEditing={() => refs.driverId.current?.focus()}
              />
            </Field>

            <Field label="Driver ID" icon="id-card-outline">
              <TextInput
                ref={refs.driverId}
                style={s.input}
                placeholder="DRV-001"
                placeholderTextColor={colors.textMuted}
                value={form.driverId}
                onChangeText={v => set('driverId', v.toUpperCase())}
                autoCapitalize="characters"
                returnKeyType="next"
                onSubmitEditing={() => refs.token.current?.focus()}
              />
            </Field>

            <Field label="API Token *" icon="key-outline">
              <TextInput
                ref={refs.token}
                style={[s.input, { flex: 1 }]}
                placeholder="Provided by dispatch"
                placeholderTextColor={colors.textMuted}
                value={form.token}
                onChangeText={v => set('token', v)}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry={!showToken}
                returnKeyType="next"
                onSubmitEditing={() => refs.baseUrl.current?.focus()}
              />
              <TouchableOpacity
                onPress={() => setShowToken(p => !p)}
                style={s.eyeBtn}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              >
                <Ionicons
                  name={showToken ? 'eye-off-outline' : 'eye-outline'}
                  size={18}
                  color={colors.textMuted}
                />
              </TouchableOpacity>
            </Field>

            <Field label="Server URL" icon="server-outline">
              <TextInput
                ref={refs.baseUrl}
                style={s.input}
                placeholder="https://api.3lakeslogistics.com"
                placeholderTextColor={colors.textMuted}
                value={form.baseUrl}
                onChangeText={v => set('baseUrl', v)}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                returnKeyType="next"
                onSubmitEditing={() => refs.phone.current?.focus()}
              />
            </Field>

            <Field label="Cell Phone (for SMS dispatch)" icon="phone-portrait-outline">
              <TextInput
                ref={refs.phone}
                style={s.input}
                placeholder="+1 (312) 555-0000"
                placeholderTextColor={colors.textMuted}
                value={form.phone}
                onChangeText={v => set('phone', v)}
                keyboardType="phone-pad"
                returnKeyType="done"
                onSubmitEditing={handleLogin}
              />
            </Field>

            <TouchableOpacity
              style={[s.btn, loading && s.btnLoading]}
              onPress={handleLogin}
              disabled={loading}
              activeOpacity={0.85}
            >
              {loading
                ? <ActivityIndicator color={colors.white} size="small" />
                : <Text style={s.btnText}>Sign In</Text>}
            </TouchableOpacity>
          </View>

          <Text style={s.footer}>
            Contact dispatch if you need your credentials.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: colors.bg },
  kav:    { flex: 1 },
  scroll: { flexGrow: 1, padding: space.base, justifyContent: 'center', paddingVertical: space.xxl },

  // Logo
  logoArea:  { alignItems: 'center', marginBottom: space.xl },
  logoMark:  {
    width: 72, height: 72, borderRadius: radius.xl,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: space.md,
    ...shadow.md,
  },
  logoTitle: { fontSize: font.xxl, fontWeight: font.extrabold, color: colors.textPrimary, letterSpacing: -0.5 },
  logoSub:   { fontSize: font.sm, color: colors.textSecondary, marginTop: 4, fontWeight: font.medium },

  // Card
  card:      {
    backgroundColor: colors.card,
    borderRadius: radius.xl,
    padding: space.xl,
    marginBottom: space.base,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardTitle: { fontSize: font.xl,   fontWeight: font.extrabold, color: colors.textPrimary, marginBottom: 4 },
  cardSub:   { fontSize: font.sm,   color: colors.textSecondary, marginBottom: space.lg, lineHeight: 20 },

  // Fields
  field:     { marginBottom: space.md },
  label:     {
    fontSize: font.xs, fontWeight: font.bold, color: colors.textSecondary,
    textTransform: 'uppercase', letterSpacing: 0.7, marginBottom: 6,
  },
  inputRow:  {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
  },
  inputIcon: { marginRight: space.sm, flexShrink: 0 },
  input: {
    flex: 1,
    paddingVertical: Platform.OS === 'ios' ? 13 : 11,
    fontSize: font.base,
    color: colors.textPrimary,
  },
  eyeBtn: { padding: space.xs },

  // Button
  btn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: 15,
    alignItems: 'center',
    marginTop: space.sm,
    ...shadow.sm,
  },
  btnLoading: { opacity: 0.7 },
  btnText: { color: colors.white, fontSize: font.base, fontWeight: font.bold, letterSpacing: 0.3 },

  footer: { textAlign: 'center', fontSize: font.xs, color: colors.textMuted, marginTop: space.sm },
});
