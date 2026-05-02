import React, { forwardRef, useImperativeHandle, useState, useRef, useCallback } from 'react';
import { Animated, Text, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, font, radius, space } from '../theme';

const CONFIGS = {
  success: { bg: colors.successLight, border: colors.successBorder, text: colors.success,  icon: '✓' },
  error:   { bg: colors.dangerLight,  border: colors.dangerBorder,  text: colors.danger,   icon: '✕' },
  warning: { bg: colors.warningLight, border: colors.warningBorder, text: colors.warning,  icon: '⚠' },
  info:    { bg: colors.primaryLight, border: colors.primaryBorder, text: colors.primary,  icon: 'ℹ' },
};

const Toast = forwardRef((_, ref) => {
  const insets = useSafeAreaInsets();
  const [queue, setQueue] = useState([]);
  const timer  = useRef(null);
  const anim   = useRef(new Animated.Value(0)).current;

  const show = useCallback((message, type = 'info') => {
    clearTimeout(timer.current);
    const cfg = CONFIGS[type] || CONFIGS.info;
    setQueue([{ message, cfg }]);

    Animated.spring(anim, {
      toValue: 1,
      useNativeDriver: true,
      tension: 120,
      friction: 10,
    }).start();

    timer.current = setTimeout(() => {
      Animated.timing(anim, {
        toValue: 0,
        duration: 250,
        useNativeDriver: true,
      }).start(() => setQueue([]));
    }, 3400);
  }, [anim]);

  useImperativeHandle(ref, () => ({ show }), [show]);

  if (queue.length === 0) return null;
  const { message, cfg } = queue[0];

  return (
    <Animated.View
      style={[
        styles.wrap,
        { bottom: insets.bottom + 80, backgroundColor: cfg.bg, borderColor: cfg.border },
        {
          opacity: anim,
          transform: [{
            translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }),
          }],
        },
      ]}
      pointerEvents="none"
    >
      <View style={[styles.iconWrap, { backgroundColor: cfg.border }]}>
        <Text style={[styles.icon, { color: cfg.text }]}>{cfg.icon}</Text>
      </View>
      <Text style={[styles.msg, { color: cfg.text }]} numberOfLines={3}>{message}</Text>
    </Animated.View>
  );
});

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: space.base,
    right: space.base,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.md,
    paddingHorizontal: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    zIndex: 9999,
    gap: space.sm,
  },
  iconWrap: {
    width: 28,
    height: 28,
    borderRadius: radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  icon: { fontSize: 13, fontWeight: font.bold },
  msg:  { flex: 1, fontSize: font.sm, fontWeight: font.medium, lineHeight: 19 },
});

export default Toast;
