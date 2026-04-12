import {
  AuthorResult,
  ChatQueryResponse,
  HealthStatus,
  QuoteResult,
  TTSPreviewResponse,
  UserPreferences,
  UserProfile,
  VoiceQueryResponse,
} from "@/lib/types";

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

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseApiError(response: Response): Promise<never> {
  const fallback = `Request failed with status ${response.status}`;
  try {
    const payload = (await response.json()) as { detail?: string } | null;
    const message = payload?.detail ?? fallback;
    throw new ApiError(message, response.status);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    const text = await response.text().catch(() => "");
    throw new ApiError(text || fallback, response.status);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(resolveApiUrl(path) as string, {
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    return parseApiError(response);
  }
  return (await response.json()) as T;
}

export async function fetchUsers(): Promise<UserProfile[]> {
  try {
    return await requestJson<UserProfile[]>("/api/users");
  } catch {
    return [];
  }
}

export async function fetchUser(userId: string): Promise<UserProfile | null> {
  try {
    return await requestJson<UserProfile>(`/api/users/${encodeURIComponent(userId)}`);
  } catch {
    return null;
  }
}

export async function fetchHealth(): Promise<HealthStatus | null> {
  try {
    return await requestJson<HealthStatus>("/api/health");
  } catch {
    return null;
  }
}

export async function fetchRandomQuote(): Promise<QuoteResult | null> {
  try {
    return await requestJson<QuoteResult | null>("/api/quotes/random");
  } catch {
    return null;
  }
}

export async function submitChatQuery(payload: {
  message: string;
  conversation_id?: string | null;
  selected_user_id?: string | null;
}): Promise<ChatQueryResponse> {
  return requestJson<ChatQueryResponse>("/api/chat/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function submitVoiceQuery(payload: {
  audio: Blob;
  filename?: string;
  conversation_id?: string | null;
  selected_user_id?: string | null;
}): Promise<VoiceQueryResponse> {
  const formData = new FormData();
  formData.append("audio", payload.audio, payload.filename ?? "recording.webm");
  if (payload.conversation_id) {
    formData.append("conversation_id", payload.conversation_id);
  }
  if (payload.selected_user_id) {
    formData.append("selected_user_id", payload.selected_user_id);
  }
  return requestJson<VoiceQueryResponse>("/api/voice/query", {
    method: "POST",
    body: formData,
  });
}

export async function registerUser(payload: {
  display_name: string;
  group_identifier?: string | null;
  pitch_scale?: number;
  speaking_rate?: number;
  energy_scale?: number;
  audio_samples: Array<{ blob: Blob; name: string }>;
}): Promise<UserProfile> {
  const formData = new FormData();
  formData.append("display_name", payload.display_name);
  if (payload.group_identifier) {
    formData.append("group_identifier", payload.group_identifier);
  }
  formData.append("pitch_scale", String(payload.pitch_scale ?? 1));
  formData.append("speaking_rate", String(payload.speaking_rate ?? 1));
  formData.append("energy_scale", String(payload.energy_scale ?? 1));
  for (const sample of payload.audio_samples) {
    formData.append("audio_samples", sample.blob, sample.name);
  }
  return requestJson<UserProfile>("/api/users/register", {
    method: "POST",
    body: formData,
  });
}

export async function updateUserPreferences(userId: string, preferences: UserPreferences): Promise<UserProfile> {
  return requestJson<UserProfile>(`/api/users/${encodeURIComponent(userId)}/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(preferences),
  });
}

export async function createTtsPreview(payload: {
  text: string;
  user_id?: string | null;
  preferences?: UserPreferences;
}): Promise<TTSPreviewResponse> {
  return requestJson<TTSPreviewResponse>("/api/tts/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function reEnrollUser(
  userId: string,
  audioSamples: Array<{ blob: Blob; name: string }>
): Promise<UserProfile> {
  const formData = new FormData();
  for (const sample of audioSamples) {
    formData.append("audio_samples", sample.blob, sample.name);
  }
  return requestJson<UserProfile>(`/api/users/${encodeURIComponent(userId)}/re-enroll`, {
    method: "POST",
    body: formData,
  });
}

export async function deleteUserProfile(userId: string): Promise<void> {
  const response = await fetch(resolveApiUrl(`/api/users/${encodeURIComponent(userId)}`) as string, {
    method: "DELETE",
  });
  if (!response.ok) {
    return parseApiError(response);
  }
}

export async function fetchPopularAuthors(limit = 20): Promise<AuthorResult[]> {
  try {
    return await requestJson<AuthorResult[]>(`/api/authors/popular?limit=${limit}`);
  } catch {
    return [];
  }
}

export async function fetchThemeQuotes(theme: string, limit = 10): Promise<QuoteResult[]> {
  try {
    return await requestJson<QuoteResult[]>(
      `/api/quotes/by-theme?theme=${encodeURIComponent(theme)}&limit=${limit}`
    );
  } catch {
    return [];
  }
}

export async function fetchAutocomplete(query: string, limit = 5): Promise<QuoteResult[]> {
  if (!query.trim()) return [];
  try {
    return await requestJson<QuoteResult[]>(
      `/api/quotes/autocomplete?query=${encodeURIComponent(query)}&limit=${limit}`
    );
  } catch {
    return [];
  }
}

export async function fetchIntelligentSearch(query: string, limit = 10): Promise<QuoteResult[]> {
  if (!query.trim()) return [];
  try {
    return await requestJson<QuoteResult[]>(
      `/api/quotes/intelligent-search?query=${encodeURIComponent(query)}&limit=${limit}`
    );
  } catch {
    return [];
  }
}

export async function fetchVoiceSearch(query: string, limit = 3): Promise<QuoteResult[]> {
  if (!query.trim()) return [];
  try {
    return await requestJson<QuoteResult[]>(
      `/api/quotes/voice-search?query=${encodeURIComponent(query)}&limit=${limit}`
    );
  } catch {
    return [];
  }
}
