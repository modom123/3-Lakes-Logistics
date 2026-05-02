import React, { useState, useContext } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AuthContext } from '../context';
import { storage } from '../storage';
import { api } from '../api';
import { colors, typography, spacing, radius } from '../theme';

export default function LoginScreen() {
  const { setAuth } = useContext(AuthContext);
  const [form, setForm] = useState({
    driverName: '',
    driverId: '',
    token: '',
    baseUrl: '',
    phone: '',
  });
  const [loading, setLoading] = useState(false);

  function set(key, val) {
    setForm(prev => ({ ...prev, [key]: val }));
  }

  async function handleLogin() {
    if (!form.driverName.trim()) {
      Alert.alert('Required', 'Please enter your name.');
      return;
    }
    if (!form.token.trim()) {
      Alert.alert('Required', 'Please enter your API token from dispatch.');
      return;
    }

    setLoading(true);
    try {
      const auth = {
        token: form.token.trim(),
        driverId: form.driverId.trim() || 'DRV-001',
        driverName: form.driverName.trim(),
        baseUrl: form.baseUrl.trim().replace(/\/$/, ''),
        phone: form.phone.trim(),
      };
      await storage.saveAuth(auth);
      if (form.phone.trim()) {
        await storage.savePhone(form.phone.trim());
      }
      api.init(auth);
      setAuth(auth);
    } catch (err) {
      Alert.alert('Error', 'Could not save credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {/* Logo */}
          <View style={styles.logoWrap}>
            <Text style={styles.logo}>🚛 3 Lakes</Text>
            <Text style={styles.logoSub}>Driver App</Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.title}>Sign In</Text>
            <Text style={styles.subtitle}>Enter the credentials provided by dispatch.</Text>

            <View style={styles.fieldGroup}>
              <Text style={styles.label}>Your Name *</Text>
              <TextInput
                style={styles.input}
                placeholder="John Smith"
                placeholderTextColor={colors.textMuted}
                value={form.driverName}
                onChangeText={v => set('driverName', v)}
                autoCapitalize="words"
                returnKeyType="next"
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text style={styles.label}>Driver ID</Text>
              <TextInput
                style={styles.input}
                placeholder="DRV-001"
                placeholderTextColor={colors.textMuted}
                value={form.driverId}
                onChangeText={v => set('driverId', v)}
                autoCapitalize="characters"
                returnKeyType="next"
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text style={styles.label}>API Token *</Text>
              <TextInput
                style={styles.input}
                placeholder="Provided by dispatch"
                placeholderTextColor={colors.textMuted}
                value={form.token}
                onChangeText={v => set('token', v)}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry
                returnKeyType="next"
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text style={styles.label}>Server URL</Text>
              <TextInput
                style={styles.input}
                placeholder="https://api.3lakeslogistics.com"
                placeholderTextColor={colors.textMuted}
                value={form.baseUrl}
                onChangeText={v => set('baseUrl', v)}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                returnKeyType="next"
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text style={styles.label}>Cell Phone (for SMS dispatches)</Text>
              <TextInput
                style={styles.input}
                placeholder="+13125550000"
                placeholderTextColor={colors.textMuted}
                value={form.phone}
                onChangeText={v => set('phone', v)}
                keyboardType="phone-pad"
                returnKeyType="done"
                onSubmitEditing={handleLogin}
              />
            </View>

            <TouchableOpacity
              style={[styles.btn, loading && styles.btnDisabled]}
              onPress={handleLogin}
              disabled={loading}
              activeOpacity={0.8}
            >
              {loading ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.btnText}>Sign In</Text>
              )}
            </TouchableOpacity>
          </View>

          <Text style={styles.footer}>
            Contact dispatch if you need your credentials.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  scroll: { flexGrow: 1, padding: spacing.lg, justifyContent: 'center' },
  logoWrap: { alignItems: 'center', marginBottom: spacing.xxl },
  logo: { fontSize: 32, fontWeight: '800', color: colors.primary, letterSpacing: -1 },
  logoSub: { fontSize: typography.base, color: colors.textSecondary, marginTop: 4, fontWeight: '600' },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.xl,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
    marginBottom: spacing.lg,
  },
  title: { fontSize: typography.xl, fontWeight: '800', color: colors.textPrimary, marginBottom: 4 },
  subtitle: { fontSize: typography.sm, color: colors.textSecondary, marginBottom: spacing.xl },
  fieldGroup: { marginBottom: spacing.md },
  label: {
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
  },
  btn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: spacing.md,
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: colors.white, fontSize: typography.base, fontWeight: '700' },
  footer: { textAlign: 'center', fontSize: typography.xs, color: colors.textMuted },
});
