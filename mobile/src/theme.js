import { Platform } from 'react-native';

// ── Color Palette ────────────────────────────────────────────────────────────

export const colors = {
  // Page & surface backgrounds
  bg:       '#F4F7FC',
  card:     '#FFFFFF',
  surface:  '#EEF3FB',
  overlay:  'rgba(10, 28, 64, 0.45)',

  // Brand blues
  primary:      '#1652A0',
  primaryDark:  '#0D3C7A',
  primaryMid:   '#1A6ACF',
  primaryLight: '#E8F1FD',
  primaryBorder:'#B3CEEE',

  // Text
  textPrimary:   '#161B2E',
  textSecondary: '#5A6578',
  textMuted:     '#8D9BB0',
  textInverse:   '#FFFFFF',

  // Status — success
  success:       '#1B7A3E',
  successMid:    '#34A853',
  successLight:  '#E6F4EA',
  successBorder: '#A8D5B5',

  // Status — warning
  warning:       '#8C4A08',
  warningMid:    '#F29D38',
  warningLight:  '#FEF3C7',
  warningBorder: '#F5CCA0',

  // Status — danger
  danger:        '#B41515',
  dangerMid:     '#E53935',
  dangerLight:   '#FEECEC',
  dangerBorder:  '#F5A3A3',

  // UI chrome
  border:    '#DDE4EF',
  separator: '#EAF0F8',
  shadow:    '#0A1C40',

  white: '#FFFFFF',
  black: '#000000',
};

// ── Typography ───────────────────────────────────────────────────────────────

export const font = {
  // Sizes
  xs:   11,
  sm:   13,
  base: 15,
  md:   16,
  lg:   18,
  xl:   22,
  xxl:  26,
  xxxl: 32,

  // Weights (strings for cross-platform compat)
  regular:     '400',
  medium:      '500',
  semibold:    '600',
  bold:        '700',
  extrabold:   '800',
  black:       '900',

  // Families
  family: Platform.select({ ios: 'SF Pro Display', android: 'Roboto', default: 'System' }),
};

// ── Spacing ──────────────────────────────────────────────────────────────────

export const space = {
  xxs:  2,
  xs:   4,
  sm:   8,
  md:   12,
  base: 16,
  lg:   20,
  xl:   24,
  xxl:  32,
  xxxl: 48,
};

// ── Radius ───────────────────────────────────────────────────────────────────

export const radius = {
  xs:   4,
  sm:   8,
  md:   12,
  lg:   16,
  xl:   20,
  full: 999,
};

// ── Shadows ──────────────────────────────────────────────────────────────────

export const shadow = {
  xs: {
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 2,
    elevation: 1,
  },
  sm: {
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },
  md: {
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.10,
    shadowRadius: 10,
    elevation: 5,
  },
  lg: {
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.14,
    shadowRadius: 20,
    elevation: 10,
  },
};
