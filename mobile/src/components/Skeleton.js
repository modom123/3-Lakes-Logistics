import React, { useEffect, useRef } from 'react';
import { Animated, View, StyleSheet } from 'react-native';
import { colors, radius } from '../theme';

export default function Skeleton({ width, height, borderRadius, style }) {
  const anim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(anim, { toValue: 1,   duration: 800, useNativeDriver: true }),
        Animated.timing(anim, { toValue: 0.4, duration: 800, useNativeDriver: true }),
      ])
    ).start();
  }, [anim]);

  return (
    <Animated.View
      style={[
        styles.base,
        { width, height, borderRadius: borderRadius ?? radius.sm, opacity: anim },
        style,
      ]}
    />
  );
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <View style={styles.card}>
      <Skeleton width="60%" height={14} style={{ marginBottom: 10 }} />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={i === lines - 1 ? '45%' : '90%'} height={11} style={{ marginBottom: 7 }} />
      ))}
    </View>
  );
}

export function SkeletonLoadRow() {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Skeleton width="75%" height={14} style={{ marginBottom: 8 }} />
        <Skeleton width="50%" height={11} style={{ marginBottom: 6 }} />
        <Skeleton width="35%" height={18} />
      </View>
      <View style={{ gap: 6, marginLeft: 12 }}>
        <Skeleton width={70} height={32} borderRadius={8} />
        <Skeleton width={70} height={32} borderRadius={8} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  base: { backgroundColor: colors.border },
  card: {
    backgroundColor: colors.card,
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  row: {
    backgroundColor: colors.card,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
});
