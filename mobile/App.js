import React, { useState, useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthContext, BadgeContext } from './src/context';
import { storage } from './src/storage';
import { api } from './src/api';
import AppNavigator from './src/navigation/AppNavigator';
import { colors } from './src/theme';

export default function App() {
  const [auth, setAuth] = useState(null);
  const [booting, setBooting] = useState(true);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    storage.getAuth().then(a => {
      if (a) {
        api.init(a);
        setAuth(a);
      }
      setBooting(false);
    });
  }, []);

  if (booting) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.white }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <AuthContext.Provider value={{ auth, setAuth }}>
        <BadgeContext.Provider value={{ unread, setUnread }}>
          <NavigationContainer>
            <StatusBar style="dark" backgroundColor={colors.white} />
            <AppNavigator />
          </NavigationContainer>
        </BadgeContext.Provider>
      </AuthContext.Provider>
    </SafeAreaProvider>
  );
}
