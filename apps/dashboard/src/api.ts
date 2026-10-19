import type { ApiFailure } from "./types";

const TOKEN_KEY = "cloudsentinel.token";

export function loadToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) ?? "";
}

export function saveToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  body: ApiFailure;

  constructor(status: number, body: ApiFailure) {
    super(body.message || `Request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function api<T>(path: string, init: RequestInit = {}, token = loadToken()): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  const body = text ? (JSON.parse(text) as ApiFailure) : {};
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  return body as T;
}
