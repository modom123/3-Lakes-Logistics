import React from 'react';
import { View, Text, StyleSheet, Platform } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';

import { useAuth, useBadge } from '../context';
import { colors, font, radius, space } from '../theme';

import LoginScreen      from '../screens/LoginScreen';
import HomeScreen       from '../screens/HomeScreen';
import LoadsScreen      from '../screens/LoadsScreen';
import LoadDetailScreen from '../screens/LoadDetailScreen';
import MessagesScreen   from '../screens/MessagesScreen';
import DocumentsScreen  from '../screens/DocumentsScreen';
import ProfileScreen    from '../screens/ProfileScreen';

const Stack = createNativeStackNavigator();
const Tab   = createBottomTabNavigator();

const TAB_CONFIG = [
  { name: 'Home',     icon: 'home',              label: 'Home'     },
  { name: 'Loads',    icon: 'cube',               label: 'Loads'    },
  { name: 'Messages', icon: 'chatbubble-ellipses', label: 'Messages' },
  { name: 'Docs',     icon: 'document-text',      label: 'Docs'     },
  { name: 'Profile',  icon: 'person-circle',      label: 'Profile'  },
];

function TabBarIcon({ name, focused, badge }) {
  return (
    <View style={styles.iconWrap}>
      <Ionicons
        name={focused ? name : `${name}-outline`}
        size={24}
        color={focused ? colors.primary : colors.textMuted}
      />
      {badge > 0 && (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{badge > 99 ? '99+' : badge}</Text>
        </View>
      )}
    </View>
  );
}

// Loads sub-stack (Loads list → Load detail) ────────────────────────────────
function LoadsStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: true,
        headerStyle:      { backgroundColor: colors.card },
        headerTintColor:  colors.primary,
        headerTitleStyle: { fontSize: font.md, fontWeight: font.bold, color: colors.textPrimary },
        headerShadowVisible: true,
        contentStyle: { backgroundColor: colors.bg },
      }}
    >
      <Stack.Screen name="LoadsList"   component={LoadsScreen}      options={{ headerShown: false }} />
      <Stack.Screen name="LoadDetail"  component={LoadDetailScreen}  options={{ title: 'Load Details', headerBackTitle: 'Loads' }} />
    </Stack.Navigator>
  );
}

// Main tab navigator ─────────────────────────────────────────────────────────
function MainTabs() {
  const { unread } = useBadge();

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor:   colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle:             styles.tabBar,
        tabBarLabelStyle:        styles.tabLabel,
        tabBarIcon: ({ focused }) => {
          const cfg = TAB_CONFIG.find(t => t.name === route.name);
          const badge = route.name === 'Messages' ? unread : 0;
          return <TabBarIcon name={cfg.icon} focused={focused} badge={badge} />;
        },
      })}
    >
      {TAB_CONFIG.map(({ name, label }) => (
        <Tab.Screen
          key={name}
          name={name}
          component={name === 'Loads' ? LoadsStack : SCREEN_MAP[name]}
          options={{ tabBarLabel: label }}
        />
      ))}
    </Tab.Navigator>
  );
}

const SCREEN_MAP = {
  Home:     HomeScreen,
  Messages: MessagesScreen,
  Docs:     DocumentsScreen,
  Profile:  ProfileScreen,
};

// Root navigator ─────────────────────────────────────────────────────────────
export default function AppNavigator() {
  const { auth } = useAuth();
  return (
    <Stack.Navigator screenOptions={{ headerShown: false, animation: 'fade' }}>
      {auth ? (
        <Stack.Screen name="Main"  component={MainTabs}    />
      ) : (
        <Stack.Screen name="Login" component={LoginScreen} />
      )}
    </Stack.Navigator>
  );
}

const styles = StyleSheet.create({
  iconWrap: { alignItems: 'center', justifyContent: 'center' },
  badge: {
    position:  'absolute',
    top:       -5,
    right:     -8,
    minWidth:  17,
    height:    17,
    borderRadius: radius.full,
    backgroundColor: colors.dangerMid,
    alignItems:      'center',
    justifyContent:  'center',
    paddingHorizontal: 3,
    borderWidth: 1.5,
    borderColor: colors.card,
  },
  badgeText: {
    color:      colors.white,
    fontSize:   9,
    fontWeight: font.bold,
    lineHeight: 13,
  },
  tabBar: {
    backgroundColor:  colors.card,
    borderTopWidth:   1,
    borderTopColor:   colors.border,
    height:           Platform.select({ ios: 82, android: 64 }),
    paddingBottom:    Platform.select({ ios: 22, android: 8 }),
    paddingTop:       8,
    elevation:        8,
    shadowColor:      colors.shadow,
    shadowOffset:     { width: 0, height: -3 },
    shadowOpacity:    0.07,
    shadowRadius:     8,
  },
  tabLabel: {
    fontSize:   10,
    fontWeight: font.semibold,
    marginTop:  2,
  },
});
