import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, StyleSheet, Alert } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Notifications from 'expo-notifications';
import * as Updates from 'expo-updates';

import { AuthContext, ToastContext, BadgeContext, NetworkContext } from './src/context';
import { authService } from './src/services/auth';
import { initHttp, invalidateToken } from './src/services/http';
import { EventEmitter } from './src/services/events';
import AppNavigator from './src/navigation/AppNavigator';
import Toast from './src/components/Toast';
import NetworkBanner from './src/components/NetworkBanner';
import { colors } from './src/theme';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge:  true,
  }),
});

export default function App() {
  const [auth,     setAuth]     = useState(null);
  const [booting,  setBooting]  = useState(true);
  const [unread,   setUnread]   = useState(0);
  const [isOnline, setIsOnline] = useState(true);

  const toastRef = useRef(null);

  const showToast = useCallback((message, type = 'info') => {
    toastRef.current?.show(message, type);
  }, []);

  // Boot: load credentials from SecureStore ─────────────────────────────────
  useEffect(() => {
    authService.load().then(a => {
      if (a) {
        initHttp({ baseUrl: a.baseUrl, token: a.token });
        setAuth(a);
      }
      setBooting(false);
    });
  }, []);

  // Handle 401 from any API call ─────────────────────────────────────────────
  useEffect(() => {
    const off = EventEmitter.on('auth:unauthorized', async () => {
      invalidateToken();
      await authService.clear();
      setAuth(null);
      showToast('Session expired — please sign in again.', 'error');
    });
    return off;
  }, [showToast]);

  // OTA update check ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (__DEV__) return; // skip in development
    (async () => {
      try {
        const update = await Updates.checkForUpdateAsync();
        if (!update.isAvailable) return;
        await Updates.fetchUpdateAsync();
        Alert.alert(
          'Update Ready',
          'A new version of 3 Lakes Driver has been downloaded. Restart to apply it.',
          [
            { text: 'Later' },
            { text: 'Restart Now', onPress: () => Updates.reloadAsync() },
          ]
        );
      } catch {
        // Silent fail — update checks are non-critical
      }
    })();
  }, []);

  // Push notification permission ─────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      const { status } = await Notifications.requestPermissionsAsync();
      if (status !== 'granted') return;
      const token = await Notifications.getExpoPushTokenAsync().catch(() => null);
      if (token) console.log('[Push Token]', token.data);
    })();
  }, []);

  if (booting) {
    return (
      <View style={styles.boot}>
        <StatusBar style="light" backgroundColor={colors.primary} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <AuthContext.Provider value={{ auth, setAuth }}>
        <ToastContext.Provider value={{ showToast }}>
          <BadgeContext.Provider value={{ unread, setUnread }}>
            <NetworkContext.Provider value={{ isOnline, setIsOnline }}>
              <NavigationContainer>
                <StatusBar style="dark" backgroundColor={colors.card} />
                <NetworkBanner onStatusChange={setIsOnline} />
                <AppNavigator />
                <Toast ref={toastRef} />
              </NavigationContainer>
            </NetworkContext.Provider>
          </BadgeContext.Provider>
        </ToastContext.Provider>
      </AuthContext.Provider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  boot: { flex: 1, backgroundColor: colors.primary },
});
