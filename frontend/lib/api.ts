import { QuoteResult, UserProfile } from "@/lib/types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function resolveApiUrl(path?: string | null): string | null {
  if (!path) {
    return null;
  }
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(resolveApiUrl(path) as string, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchUsers(): Promise<UserProfile[]> {
  try {
    return await fetchJson<UserProfile[]>("/api/users");
  } catch {
    return [];
  }
}

export async function fetchUser(userId: string): Promise<UserProfile | null> {
  try {
    return await fetchJson<UserProfile>(`/api/users/${encodeURIComponent(userId)}`);
  } catch {
    return null;
  }
}

export async function fetchRandomQuote(): Promise<QuoteResult | null> {
  try {
    return await fetchJson<QuoteResult | null>("/api/quotes/random");
  } catch {
    return null;
  }
}
