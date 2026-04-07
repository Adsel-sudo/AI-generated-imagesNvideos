import { request } from "@/src/lib/api/client";

export interface AuthUser {
  id: string;
  username: string;
}

interface AuthResponse {
  user: AuthUser;
}

export function fetchCurrentUser() {
  return request<AuthResponse>("/api/auth/me");
}

export function login(payload: { username: string; password: string }) {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: payload,
  });
}

export function logout() {
  return request<{ ok: boolean }>("/api/auth/logout", {
    method: "POST",
  });
}
