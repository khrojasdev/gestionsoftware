/** Thin client for the Trazo REST API (`/api/v1`). */

const RAW_BASE = (import.meta.env.VITE_API_URL ?? "").trim();
export const API_BASE = RAW_BASE.replace(/\/$/, "");
const TOKEN_KEY = "trazo.token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

let token: string | null = readToken();
let onUnauthorized: (() => void) | null = null;

export function setToken(value: string | null): void {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage may be unavailable (private mode); keep the in-memory token */
  }
}

export function getToken(): string | null {
  return token;
}

export function handleUnauthorized(callback: () => void): void {
  onUnauthorized = callback;
}

type Options = { method?: string; body?: unknown; form?: FormData; raw?: boolean };

export async function request<T>(path: string, options: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.form) body = options.form;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1${path}`, { method: options.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "NETWORK", "No fue posible conectar con el servidor. ¿Está corriendo el backend?");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    if (response.status === 401 && onUnauthorized && !path.startsWith("/auth/login")) onUnauthorized();
    throw new ApiError(response.status, error?.code ?? "HTTP_ERROR", error?.message ?? `Error ${response.status}`, error?.details);
  }
  if (!options.raw && payload && typeof payload === "object" && "data" in (payload as Record<string, unknown>)) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body ?? {} }),
  put: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: body ?? {} }),
  patch: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body ?? {} }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T,>(path: string, file: File, extra?: Record<string, string>) => {
    const form = new FormData();
    form.append("file", file);
    Object.entries(extra ?? {}).forEach(([key, value]) => form.append(key, value));
    return request<T>(path, { method: "POST", form });
  },
};

/** Download a protected file (evidence) using the bearer token. */
export async function downloadFile(path: string, fileName: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) throw new ApiError(response.status, "DOWNLOAD", "No fue posible descargar el archivo");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function templateUrl(): string {
  return `${API_BASE}/api/v1/import-template`;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const details = error.details;
    if (Array.isArray(details) && details.length && typeof details[0] === "object" && details[0] && "message" in details[0]) {
      return `${error.message}: ${(details as { message: string }[]).map((item) => item.message).join("; ")}`;
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}
