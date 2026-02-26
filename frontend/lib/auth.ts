import type { UserInfo } from "./types";

const TOKEN_KEY = "ebilling_token";
const ROLE_KEY = "ebilling_role";
const USER_KEY = "ebilling_user";

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(USER_KEY);
}

export function setRole(role: string): void {
  localStorage.setItem(ROLE_KEY, role);
}

export function getRole(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ROLE_KEY);
}

export function setUserInfo(user: UserInfo): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getUserInfo(): UserInfo | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as UserInfo) : null;
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export function isCarrierRole(): boolean {
  const role = getRole();
  return role === "CARRIER_ADMIN" || role === "CARRIER_REVIEWER";
}

export function isCarrierAdmin(): boolean {
  return getRole() === "CARRIER_ADMIN";
}

export function isSupplier(): boolean {
  return getRole() === "SUPPLIER";
}
