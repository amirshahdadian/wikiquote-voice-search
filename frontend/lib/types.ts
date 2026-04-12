export type AuthorResult = {
  author_name: string;
  quote_count: number;
};

export type QuoteResult = {
  quote_text: string;
  author_name: string;
  source_title: string;
  relevance_score?: number | null;
  search_type?: string | null;
  match_position?: string | null;
};

export type UserPreferences = {
  pitch_scale: number;
  speaking_rate: number;
  energy_scale: number;
  style?: string;
};

export type UserProfile = {
  user_id: string;
  display_name: string;
  group_identifier?: string | null;
  has_embedding: boolean;
  preferences?: UserPreferences | null;
};

export type RecognizedUser = {
  user_id: string;
  display_name: string;
  confidence?: number | null;
  source: string;
};

export type HealthStatus = {
  search: boolean;
  asr: boolean;
  speaker_id: boolean;
  tts: boolean;
  sqlite: boolean;
};

export type ChatQueryResponse = {
  conversation_id: string;
  recognized_user?: RecognizedUser | null;
  intent_type: string;
  response_text: string;
  best_quote?: QuoteResult | null;
  related_quotes: QuoteResult[];
  audio_url?: string | null;
  warnings: string[];
};

export type VoiceQueryResponse = ChatQueryResponse & {
  transcript: string;
  normalized_transcript: string;
};

export type TTSPreviewResponse = {
  audio_url?: string | null;
  warnings: string[];
};

export type LocalAudioSample = {
  id: string;
  name: string;
  blob: Blob;
  url: string;
  source: "recorded" | "uploaded";
};
