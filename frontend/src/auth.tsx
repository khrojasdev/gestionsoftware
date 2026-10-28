import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, getToken, handleUnauthorized, setToken } from "./api";
import type { LoginResponse, Role, User } from "./types";

type AuthState = {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  isAdmin: boolean;
  isManager: boolean;
  isMember: boolean;
  primaryRole: Role | null;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    handleUnauthorized(logout);
    if (!getToken()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setReady(true);
      return;
    }
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<LoginResponse>("/auth/login", { email, password });
    setToken(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  const value = useMemo<AuthState>(() => {
    const roles = user?.roles ?? [];
    const isAdmin = roles.includes("ADMINISTRADOR");
    const isManager = isAdmin || roles.includes("JEFE_DE_PROYECTO");
    const primaryRole: Role | null = isAdmin ? "ADMINISTRADOR" : roles.includes("JEFE_DE_PROYECTO") ? "JEFE_DE_PROYECTO" : roles.length ? "INTEGRANTE" : null;
    return { user, ready, login, logout, isAdmin, isManager, isMember: !isManager && roles.includes("INTEGRANTE"), primaryRole };
  }, [user, ready, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth fuera de AuthProvider");
  return value;
}
