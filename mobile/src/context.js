import { createContext, useContext } from 'react';

export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

export const BadgeContext = createContext({ unread: 0, setUnread: () => {} });

export function useBadge() {
  return useContext(BadgeContext);
}
