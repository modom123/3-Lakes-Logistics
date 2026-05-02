import { createContext, useContext } from 'react';

// Auth context ──────────────────────────────────────────────────────────────
export const AuthContext = createContext({
  auth: null,
  setAuth: () => {},
});
export const useAuth = () => useContext(AuthContext);

// Toast context ─────────────────────────────────────────────────────────────
// shape: (message: string, type?: 'success'|'error'|'info'|'warning') => void
export const ToastContext = createContext({ showToast: () => {} });
export const useToast = () => useContext(ToastContext);

// Badge context ─────────────────────────────────────────────────────────────
export const BadgeContext = createContext({ unread: 0, setUnread: () => {} });
export const useBadge = () => useContext(BadgeContext);

// Network context ───────────────────────────────────────────────────────────
export const NetworkContext = createContext({ isOnline: true });
export const useNetwork = () => useContext(NetworkContext);
