import React, { useEffect, useRef, useState } from 'react';
import { Animated, Text, StyleSheet, AppState } from 'react-native';
import { colors, font, space } from '../theme';

export default function NetworkBanner({ onStatusChange }) {
  const [offline, setOffline] = useState(false);
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let interval;

    async function check() {
      try {
        const res = await fetch('https://www.google.com/generate_204', {
          method: 'HEAD',
          cache: 'no-store',
          signal: AbortSignal.timeout?.(4000) ?? (() => {
            const c = new AbortController();
            setTimeout(() => c.abort(), 4000);
            return c.signal;
          })(),
        });
        setOnline(res.status < 400);
      } catch {
        setOnline(false);
      }
    }

    function setOnline(val) {
      const isOff = !val;
      setOffline(isOff);
      onStatusChange?.(val);
      Animated.timing(anim, {
        toValue: isOff ? 1 : 0,
        duration: 300,
        useNativeDriver: false,
      }).start();
    }

    // check every 15s
    interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, [anim, onStatusChange]);

  const height = anim.interpolate({ inputRange: [0, 1], outputRange: [0, 36] });

  if (!offline) return null;

  return (
    <Animated.View style={[styles.banner, { height }]}>
      <Text style={styles.text}>⚠  No internet connection</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.warningMid,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  text: {
    color: colors.white,
    fontSize: font.xs,
    fontWeight: font.bold,
    letterSpacing: 0.3,
  },
});
