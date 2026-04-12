"use client";

import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Fingerprint,
  Loader2,
  Mic,
  MicOff,
  Plus,
  Quote,
  Sparkles,
  Trash2,
  Upload,
  User,
  Users,
  Volume2,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type {
  ChatQueryResponse,
  HealthStatus,
  UserPreferences,
  UserProfile,
  VoiceQueryResponse,
} from "@/lib/types";
import {
  fetchHealth,
  registerUser,
  resolveApiUrl,
  submitChatQuery,
  submitVoiceQuery,
} from "@/lib/api";
import QuoteCard from "@/components/quote-card";
import VoiceWaveform from "@/components/voice-waveform";

const cn = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(" ");

// ── Types ─────────────────────────────────────────────────────────────────────

type VoiceState = "idle" | "listening" | "processing";

interface RecordedSample {
  id: string;
  blob: Blob;
  url: string;
  name: string;
}

interface ChatMessage {
  id: string;
  query: string;
  userId?: string;
  userName?: string;
  isVoice?: boolean;
  transcript?: string;
  response?: ChatQueryResponse | VoiceQueryResponse;
  isLoading: boolean;
  error?: string;
}

// ── Avatar color pool ──────────────────────────────────────────────────────────

const AVATAR_COLORS = [
  "bg-violet-600/70",
  "bg-blue-600/70",
  "bg-emerald-600/70",
  "bg-amber-600/70",
  "bg-rose-600/70",
  "bg-cyan-600/70",
  "bg-indigo-600/70",
  "bg-teal-600/70",
];

function avatarColor(userId?: string): string {
  if (!userId) return "bg-white/10";
  let h = 0;
  for (let i = 0; i < userId.length; i++) h = (h * 31 + userId.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

function userInitials(name?: string): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

// ── Stable replay helper (no state deps) ──────────────────────────────────────
function replayAudio(audioUrl: string) {
  const url = resolveApiUrl(audioUrl);
  if (url) new Audio(url).play().catch(() => {});
}

// ── Health dots ────────────────────────────────────────────────────────────────

function HealthDots({ health }: { health: HealthStatus | null }) {
  if (!health) return null;
  const services: [string, boolean][] = [
    ["Search", health.search],
    ["ASR",    health.asr],
    ["TTS",    health.tts],
    ["ID",     health.speaker_id],
    ["DB",     health.sqlite],
  ];
  return (
    <div className="flex items-center gap-1.5">
      {services.map(([label, ok]) => (
        <div key={label} className="flex items-center gap-1 group relative">
          <span className={cn("status-dot", ok ? "status-dot-online" : "status-dot-offline")} />
          <span className="text-[10px] text-white/30 group-hover:text-white/50 transition-colors hidden sm:block">
            {label}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

const NEXT_SUGGESTIONS = [
  "To be, or not to be,",
  "It was the best of times",
  "I have a dream that one",
  "The only thing we have to fear",
  "That's one small step for",
  "In the beginning God created",
];

interface MessageBubbleProps {
  msg: ChatMessage;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

function MessageBubble({ msg, setQuery, inputRef }: MessageBubbleProps) {
  const hasQuery = msg.query || msg.isVoice;
  const userColor = avatarColor(msg.userId);
  const initials = userInitials(msg.userName);
  const displayName = msg.userName ?? "Anyone";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col gap-2"
    >
      {/* User query bubble */}
      {hasQuery && (
        <div className="flex items-end justify-end gap-2.5">
          <div className="flex flex-col items-end gap-1 max-w-[80%]">
            <span className="text-[10px] text-white/30 pr-1">{displayName}</span>
            <div className="rounded-2xl rounded-br-sm bg-violet-600/25 border border-violet-500/20 px-4 py-2.5">
              {msg.isVoice && !msg.query ? (
                <span className="flex items-center gap-1.5 text-sm text-white/50 italic">
                  <Mic size={11} className="text-violet-400" />
                  Voice query…
                </span>
              ) : (
                <p className="text-sm text-white/85 leading-relaxed">
                  {msg.isVoice && (
                    <Mic size={10} className="text-violet-400/70 inline mr-1.5 mb-0.5" />
                  )}
                  {msg.query}
                </p>
              )}
            </div>
          </div>
          <div className={cn(
            "w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-[10px] font-bold text-white/80 mb-0.5",
            userColor
          )}>
            {initials}
          </div>
        </div>
      )}

      {/* System response bubble */}
      <div className="flex items-start gap-2.5">
        <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-white/[0.06] border border-white/[0.08] mt-0.5">
          <Quote size={11} className="text-violet-400" />
        </div>

        <div className="flex-1 flex flex-col gap-2 min-w-0">
          {/* Loading */}
          {msg.isLoading && (
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-white/[0.04] border border-white/[0.07] px-4 py-3 w-fit">
              <Loader2 size={13} className="text-violet-400/70 animate-spin" />
              <span className="text-xs text-white/40">Finding quote…</span>
            </div>
          )}

          {/* Error */}
          {msg.error && (
            <div className="flex items-start gap-2 rounded-2xl rounded-tl-sm bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-300 max-w-md">
              <XCircle size={13} className="shrink-0 mt-0.5 text-red-400" />
              {msg.error}
            </div>
          )}

          {/* Response */}
          {!msg.isLoading && msg.response && (
            <div className="flex flex-col gap-2">
              {/* Warnings */}
              {msg.response.warnings?.length > 0 && (
                <div className="flex items-start gap-2 rounded-xl bg-amber-500/10 border border-amber-500/20 px-3 py-2 text-xs text-amber-200/80">
                  <AlertTriangle size={12} className="shrink-0 mt-0.5 text-amber-400" />
                  <div className="flex flex-col gap-0.5">
                    {msg.response.warnings.map((w, i) => <span key={i}>{w}</span>)}
                  </div>
                </div>
              )}

              {/* Speaker recognized */}
              {msg.response.recognized_user && (
                <span className="inline-flex items-center gap-1.5 self-start rounded-full px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-300/80 font-medium">
                  <CheckCircle2 size={9} />
                  {msg.response.recognized_user.display_name} recognized
                </span>
              )}

              {/* Primary quote */}
              {msg.response.best_quote ? (
                <QuoteCard quote={msg.response.best_quote} variant="primary" audioUrl={msg.response.audio_url} />
              ) : (
                <div className="rounded-2xl rounded-tl-sm glass ring-1 ring-white/5 px-4 py-3 text-sm text-white/45 max-w-sm">
                  No matching quote found. Try a different fragment.
                </div>
              )}

              {/* Related quotes */}
              {msg.response.related_quotes?.length > 0 && (
                <div className="flex flex-col gap-1.5 mt-0.5">
                  <span className="text-[10px] text-white/25 font-semibold uppercase tracking-[0.2em] px-0.5">
                    Related
                  </span>
                  {msg.response.related_quotes.slice(0, 2).map((q, i) => (
                    <QuoteCard key={i} quote={q} variant="secondary" />
                  ))}
                </div>
              )}

              {/* Replay + next suggestions */}
              <div className="flex flex-col gap-3 mt-1">
                {msg.response.audio_url && (
                  <button
                    onClick={() => replayAudio(msg.response!.audio_url!)}
                    className="self-start flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium text-white/40 hover:text-white/70 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.07] transition-all duration-200"
                  >
                    <Volume2 size={10} /> Replay
                  </button>
                )}
                <div className="flex flex-col gap-2">
                  <span className="text-[10px] text-white/20 font-semibold uppercase tracking-[0.18em]">
                    Try next
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {NEXT_SUGGESTIONS.map((frag) => (
                      <button
                        key={frag}
                        onClick={() => { setQuery(frag); inputRef.current?.focus(); }}
                        className={cn(
                          "rounded-full px-3.5 py-1.5 text-sm transition-all duration-200",
                          "bg-white/[0.04] hover:bg-violet-600/15 border border-white/[0.07] hover:border-violet-500/25",
                          "text-white/45 hover:text-white/85 font-quote italic"
                        )}
                      >
                        {frag}…
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ── Input form ────────────────────────────────────────────────────────────────
// Module-level component so its identity is stable across parent re-renders.
// If defined inside MainShell, React sees a new type on every render and
// unmounts/remounts the input, losing focus on every keystroke.

interface InputFormProps {
  query: string;
  setQuery: (v: string) => void;
  isLoading: boolean;
  voiceState: VoiceState;
  onSubmit: (e?: FormEvent) => void;
  onVoiceClick: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  large?: boolean;
}

function InputForm({
  query, setQuery, isLoading, voiceState,
  onSubmit, onVoiceClick, onKeyDown, inputRef,
  large = false,
}: InputFormProps) {
  const inputPy  = large ? "py-5"    : "py-4";
  const inputText = large ? "text-lg" : "text-base";
  const btnSize  = large ? "p-3"     : "p-2.5";
  const iconSize = large ? 20        : 17;
  const micSize  = large ? "w-14 h-14" : "w-12 h-12";

  return (
    <form onSubmit={onSubmit} className="flex items-center gap-3">
      {/* Voice button */}
      <div className="relative flex items-center justify-center shrink-0">
        {voiceState === "listening" && (
          <>
            <span className="absolute inset-0 rounded-full bg-red-500/30 animate-[pulse-ring_1.8s_ease-out_infinite]" />
            <span className="absolute inset-0 rounded-full bg-red-500/15 animate-[pulse-ring_1.8s_ease-out_0.6s_infinite]" />
          </>
        )}
        <motion.button
          type="button"
          whileTap={{ scale: 0.9 }}
          onClick={onVoiceClick}
          disabled={voiceState === "processing" || isLoading}
          className={cn(
            "relative z-10 flex items-center justify-center rounded-full transition-all duration-300 shrink-0 ring-1",
            micSize,
            voiceState === "idle" &&
              "bg-white/[0.07] hover:bg-violet-600/25 ring-white/[0.10] hover:ring-violet-500/30",
            voiceState === "listening" &&
              "bg-red-600/80 ring-red-500/50 shadow-[0_0_20px_rgba(239,68,68,0.35)]",
            voiceState === "processing" &&
              "bg-white/[0.05] ring-white/10 cursor-wait"
          )}
          aria-label={
            voiceState === "idle" ? "Start voice query"
            : voiceState === "listening" ? "Stop recording"
            : "Processing…"
          }
        >
          {voiceState === "idle" && <Mic size={iconSize} className="text-white/60" />}
          {voiceState === "listening" && <VoiceWaveform active amplitude={1.0} />}
          {voiceState === "processing" && (
            <Loader2 size={iconSize - 2} className="text-white/50 animate-spin" />
          )}
        </motion.button>
      </div>

      {/* Text input */}
      <div className="relative flex-1">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Type part of a quote…"
          className={cn("input-glass pr-14", inputPy, inputText)}
          disabled={isLoading || voiceState !== "idle"}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="submit"
          disabled={!query.trim() || isLoading || voiceState !== "idle"}
          className={cn(
            "absolute right-2 top-1/2 -translate-y-1/2 rounded-xl bg-violet-600 hover:bg-violet-500",
            "disabled:opacity-30 disabled:cursor-not-allowed text-white transition-all duration-200",
            btnSize
          )}
          aria-label="Send"
        >
          {isLoading ? (
            <Loader2 size={iconSize - 2} className="animate-spin" />
          ) : (
            <svg width={iconSize - 2} height={iconSize - 2} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2.5"
              strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="M22 2L11 13" />
              <path d="M22 2L15 22 11 13 2 9l20-7z" />
            </svg>
          )}
        </button>
      </div>
    </form>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface MainShellProps {
  initialUsers: UserProfile[];
}

export default function MainShell({ initialUsers }: MainShellProps) {
  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [query, setQuery] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [selectedUserId, setSelectedUserId] = useState<string | undefined>();
  const [isLoading, setIsLoading] = useState(false);

  // Voice state
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Users / health
  const [users, setUsers] = useState<UserProfile[]>(initialUsers);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [showUserDropdown, setShowUserDropdown] = useState(false);

  // Register modal
  const [showRegister, setShowRegister] = useState(false);

  // Refs
  const inputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const userDropdownRef = useRef<HTMLDivElement>(null);

  // ── Auto-scroll on new messages ────────────────────────────────────────────

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Health poll ────────────────────────────────────────────────────────────

  useEffect(() => {
    async function checkHealth() {
      setHealth(await fetchHealth());
    }
    checkHealth();
    const id = setInterval(checkHealth, 30_000);
    return () => clearInterval(id);
  }, []);

  // ── Close dropdown on outside click ───────────────────────────────────────

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        userDropdownRef.current &&
        !userDropdownRef.current.contains(e.target as Node)
      ) {
        setShowUserDropdown(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Auto-play TTS audio when a new response arrives ────────────────────────

  useEffect(() => {
    if (messages.length === 0) return;
    const last = messages[messages.length - 1];
    if (!last.isLoading && last.response?.audio_url) {
      const url = resolveApiUrl(last.response.audio_url);
      if (url) {
        const audio = new Audio(url);
        audio.play().catch(() => {});
      }
    }
  }, [messages]);

  // ── Helpers ────────────────────────────────────────────────────────────────

  function resolveUser(userId?: string) {
    return userId ? users.find((u) => u.user_id === userId) : undefined;
  }

  // ── Text query ─────────────────────────────────────────────────────────────

  async function sendTextQuery(text: string) {
    if (!text.trim() || isLoading) return;
    const user = resolveUser(selectedUserId);
    const msgId = `msg-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      {
        id: msgId,
        query: text.trim(),
        userId: selectedUserId,
        userName: user?.display_name,
        isVoice: false,
        isLoading: true,
      },
    ]);
    setIsLoading(true);

    try {
      const data = await submitChatQuery({
        message: text.trim(),
        conversation_id: conversationId,
        selected_user_id: selectedUserId,
      });
      setConversationId(data.conversation_id);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, isLoading: false, response: data } : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                isLoading: false,
                error: err instanceof Error ? err.message : "Something went wrong",
              }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleSearch(e?: FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;
    sendTextQuery(query);
    setQuery("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  }

  // ── Voice recording ────────────────────────────────────────────────────────

  async function startRecording() {
    if (voiceState !== "idle") return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setVoiceState("processing");
        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        await sendVoiceQuery(blob, mimeType);
      };

      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setVoiceState("listening");
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          query: "",
          isLoading: false,
          error: "Microphone access denied. Please allow microphone permissions.",
        },
      ]);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && voiceState === "listening") {
      mediaRecorderRef.current.stop();
    }
  }

  function handleVoiceButtonClick() {
    if (voiceState === "idle") startRecording();
    else if (voiceState === "listening") stopRecording();
  }

  async function sendVoiceQuery(blob: Blob, mimeType: string) {
    const msgId = `msg-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: msgId,
        query: "",
        userId: selectedUserId,
        userName: resolveUser(selectedUserId)?.display_name,
        isVoice: true,
        isLoading: true,
      },
    ]);
    setIsLoading(true);

    try {
      const ext = mimeType.includes("webm") ? "webm" : "ogg";
      const data = await submitVoiceQuery({
        audio: blob,
        filename: `recording.${ext}`,
        conversation_id: conversationId,
        selected_user_id: selectedUserId,
      });
      setConversationId(data.conversation_id);

      // Resolve user from recognized speaker if not pre-selected
      const resolvedUser =
        data.recognized_user ??
        (selectedUserId ? resolveUser(selectedUserId) : undefined);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                query: data.transcript ?? "",
                userId: resolvedUser?.user_id ?? selectedUserId,
                userName: resolvedUser?.display_name ?? resolveUser(selectedUserId)?.display_name,
                isLoading: false,
                response: data,
              }
            : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                isLoading: false,
                error: err instanceof Error ? err.message : "Voice query failed",
              }
            : m
        )
      );
    } finally {
      setVoiceState("idle");
      setIsLoading(false);
    }
  }

  // ── Derived ────────────────────────────────────────────────────────────────

  const selectedUser = users.find((u) => u.user_id === selectedUserId);

  // ── Render ─────────────────────────────────────────────────────────────────

  const hasMessages = messages.length > 0;

  return (
    <div className="relative h-dvh w-full flex flex-col overflow-hidden">
      {/* ── Header ── */}
      <header className="flex-none flex items-center justify-between px-5 md:px-8 py-4 border-b border-white/[0.06] glass-elevated z-20">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-violet-600/20 border border-violet-500/30">
            <Quote size={14} className="text-violet-400" />
          </div>
          <div className="flex flex-col leading-none">
            <span className="text-sm font-semibold tracking-tight text-white/90">
              WikiQuote{" "}
              <span className="gradient-text-violet font-bold">Voice</span>
            </span>
            <span className="text-[10px] text-white/25 mt-0.5 hidden sm:block">
              Quote auto-complete · Speaker-aware TTS
            </span>
          </div>
        </div>

        {/* Right controls */}
        <div className="flex items-center gap-3">
          <HealthDots health={health} />

          {/* User selector */}
          <div className="relative" ref={userDropdownRef}>
            <button
              onClick={() => setShowUserDropdown((v) => !v)}
              className={cn(
                "flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm transition-all duration-300",
                "bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.08] hover:border-white/[0.14]",
                selectedUser ? "text-white/90" : "text-white/40"
              )}
            >
              <User size={13} />
              <span className="max-w-[90px] truncate hidden sm:block">
                {selectedUser ? selectedUser.display_name : "Anyone"}
              </span>
              <ChevronDown
                size={12}
                className={cn(
                  "text-white/40 transition-transform duration-200",
                  showUserDropdown && "rotate-180"
                )}
              />
            </button>

            <AnimatePresence>
              {showUserDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -8, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -8, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-full mt-2 w-48 glass-elevated rounded-xl border border-white/[0.10] shadow-glass-lg z-50 overflow-hidden"
                >
                  <button
                    onClick={() => {
                      setSelectedUserId(undefined);
                      setShowUserDropdown(false);
                    }}
                    className={cn(
                      "w-full text-left px-3 py-2.5 text-sm transition-colors duration-150",
                      !selectedUserId
                        ? "text-violet-300 bg-violet-500/10"
                        : "text-white/60 hover:text-white hover:bg-white/[0.06]"
                    )}
                  >
                    Anyone
                  </button>
                  {users.map((u) => (
                    <button
                      key={u.user_id}
                      onClick={() => {
                        setSelectedUserId(u.user_id);
                        setShowUserDropdown(false);
                      }}
                      className={cn(
                        "w-full text-left px-3 py-2.5 text-sm transition-colors duration-150 flex items-center justify-between gap-2",
                        selectedUserId === u.user_id
                          ? "text-violet-300 bg-violet-500/10"
                          : "text-white/60 hover:text-white hover:bg-white/[0.06]"
                      )}
                    >
                      <span className="truncate">{u.display_name}</span>
                      {u.has_embedding && (
                        <span className="text-[9px] text-emerald-400/70 font-semibold uppercase tracking-wide shrink-0">
                          ID
                        </span>
                      )}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Advanced features */}
          <Link
            href="/advanced"
            className="btn-secondary py-1.5 px-3 text-xs"
            title="Advanced search features"
          >
            <Sparkles size={13} />
            <span className="hidden sm:block">Advanced</span>
          </Link>

          {/* Manage users */}
          <Link
            href="/users"
            className="btn-secondary py-1.5 px-3 text-xs"
            title="Manage enrolled users"
          >
            <Users size={13} />
            <span className="hidden sm:block">Users</span>
          </Link>

          {/* Add user */}
          <button
            onClick={() => setShowRegister(true)}
            className="btn-primary py-1.5 px-3 text-xs"
            title="Register new user"
          >
            <Plus size={13} />
            <span className="hidden sm:block">Add user</span>
          </button>
        </div>
      </header>

      {/* ── Body: switches between centered (empty) and chat (active) ── */}
      <LayoutGroup>
        <AnimatePresence mode="popLayout" initial={false}>
          {!hasMessages ? (
            /* ── Empty state: centered prompt ── */
            <motion.div
              key="empty"
              className="flex-1 flex flex-col items-center justify-center px-4 md:px-8 pb-6 min-h-0 overflow-y-auto"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -16, transition: { duration: 0.2 } }}
            >
              <div className="w-full max-w-2xl flex flex-col items-center gap-12">

                {/* Hero */}
                <motion.div
                  className="flex flex-col items-center text-center"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                >
                  <div className="w-24 h-24 rounded-3xl bg-violet-600/15 border border-violet-500/20 flex items-center justify-center mb-7">
                    <Quote size={42} className="text-violet-400/70" />
                  </div>
                  <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-white/90 mb-5">
                    <span className="gradient-text">Quote Auto-Complete</span>
                  </h1>
                  <p className="text-white/55 text-lg md:text-xl max-w-lg leading-relaxed">
                    Type the beginning of any quote — the system finds the full text and reads it back in your personalized voice.
                  </p>
                </motion.div>

                {/* Capability pills */}
                <motion.div
                  className="flex flex-wrap justify-center gap-3"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
                >
                  {[
                    { icon: <Mic size={20} className="text-violet-400" />, label: "Voice queries", desc: "Speak or type" },
                    { icon: <Fingerprint size={20} className="text-emerald-400" />, label: "Speaker ID", desc: "Auto-identifies you" },
                    { icon: <Volume2 size={20} className="text-amber-400" />, label: "Personalized TTS", desc: "Your assigned voice" },
                    { icon: <BookOpen size={20} className="text-sky-400" />, label: "WikiQuote DB", desc: "Thousands of quotes" },
                  ].map(({ icon, label, desc }) => (
                    <div
                      key={label}
                      className="flex items-center gap-3.5 rounded-xl px-5 py-4 bg-white/[0.05] border border-white/[0.09] text-left"
                    >
                      <span className="shrink-0">{icon}</span>
                      <div className="flex flex-col">
                        <span className="text-base font-semibold text-white/80">{label}</span>
                        <span className="text-sm text-white/40 mt-0.5">{desc}</span>
                      </div>
                    </div>
                  ))}
                </motion.div>

                {/* Input — centered; FLIP-animates to bottom on first message */}
                <motion.div
                  layoutId="chat-input"
                  className="w-full"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                >
                  <InputForm
                    large
                    query={query}
                    setQuery={setQuery}
                    isLoading={isLoading}
                    voiceState={voiceState}
                    onSubmit={handleSearch}
                    onVoiceClick={handleVoiceButtonClick}
                    onKeyDown={handleKeyDown}
                    inputRef={inputRef}
                  />
                  {voiceState !== "idle" && (
                    <p className="text-center text-base mt-3">
                      {voiceState === "listening" && (
                        <span className="text-red-400/80">Recording — click mic to stop</span>
                      )}
                      {voiceState === "processing" && (
                        <span className="text-violet-400/80">Processing voice…</span>
                      )}
                    </p>
                  )}
                </motion.div>

                {/* Example partial quotes */}
                <motion.div
                  className="w-full flex flex-col items-center gap-5"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
                >
                  <p className="text-sm text-white/30 font-semibold uppercase tracking-[0.2em]">
                    Try these
                  </p>
                  <div className="flex flex-wrap justify-center gap-3">
                    {[
                      "To be, or not to be,",
                      "Ask not what your country",
                      "It was the best of times",
                      "I have a dream that one",
                      "The only thing we have to fear",
                      "That's one small step for",
                    ].map((ex) => (
                      <button
                        key={ex}
                        onClick={() => {
                          setQuery(ex);
                          inputRef.current?.focus();
                        }}
                        className={cn(
                          "rounded-full px-5 py-2.5 text-base font-medium transition-all duration-200",
                          "bg-white/[0.05] hover:bg-violet-600/15 border border-white/[0.09] hover:border-violet-500/30",
                          "text-white/55 hover:text-white/90 font-quote italic"
                        )}
                      >
                        {ex}…
                      </button>
                    ))}
                  </div>
                </motion.div>

              </div>
            </motion.div>
          ) : (
            /* ── Active state: chat thread + bottom bar ── */
            <motion.div
              key="chat"
              className="flex-1 flex flex-col min-h-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              {/* Chat thread */}
              <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 min-h-0">
                <div className="mx-auto w-full max-w-2xl flex flex-col gap-5">
                  {messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} setQuery={setQuery} inputRef={inputRef} />
                  ))}
                  <div ref={chatEndRef} />
                </div>
              </div>

              {/* Bottom input bar — animates in from center via layoutId */}
              <motion.div
                layoutId="chat-input"
                className="flex-none border-t border-white/[0.06] glass-elevated px-4 md:px-8 py-5"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
              >
                <div className="mx-auto w-full max-w-2xl">
                  <InputForm
                    query={query}
                    setQuery={setQuery}
                    isLoading={isLoading}
                    voiceState={voiceState}
                    onSubmit={handleSearch}
                    onVoiceClick={handleVoiceButtonClick}
                    onKeyDown={handleKeyDown}
                    inputRef={inputRef}
                  />
                  {voiceState !== "idle" && (
                    <p className="text-center text-[11px] mt-2">
                      {voiceState === "listening" && (
                        <span className="text-red-400/80">Recording — click mic to stop</span>
                      )}
                      {voiceState === "processing" && (
                        <span className="text-violet-400/80">Processing voice…</span>
                      )}
                    </p>
                  )}
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </LayoutGroup>

      {/* ── Register modal ── */}
      <AnimatePresence>
        {showRegister && (
          <RegisterModal
            onClose={() => setShowRegister(false)}
            onSuccess={(user) => {
              setUsers((prev) => [...prev, user]);
              setSelectedUserId(user.user_id);
              setShowRegister(false);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Register modal ─────────────────────────────────────────────────────────────

interface RegisterModalProps {
  onClose: () => void;
  onSuccess: (user: UserProfile) => void;
}

type RegisterStep = "form" | "recording" | "submitting" | "done";

function RegisterModal({ onClose, onSuccess }: RegisterModalProps) {
  const [step, setStep] = useState<RegisterStep>("form");
  const [displayName, setDisplayName] = useState("");
  const [preferences, setPreferences] = useState<UserPreferences>({
    pitch_scale: 1.0,
    speaking_rate: 1.0,
    energy_scale: 1.0,
    style: "",
  });
  const [samples, setSamples] = useState<RecordedSample[]>([]);
  const [recordingState, setRecordingState] = useState<"idle" | "recording">("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function startSampleRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(blob);
        const id = `rec-${Date.now()}`;
        setSamples((prev) => [
          ...prev,
          { id, blob, url, name: `Recording ${prev.length + 1}` },
        ]);
        setRecordingState("idle");
      };

      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setRecordingState("recording");
    } catch {
      setSubmitError("Microphone access denied.");
    }
  }

  function stopSampleRecording() {
    if (mediaRecorderRef.current && recordingState === "recording") {
      mediaRecorderRef.current.stop();
    }
  }

  function removeSample(id: string) {
    setSamples((prev) => {
      const s = prev.find((x) => x.id === id);
      if (s) URL.revokeObjectURL(s.url);
      return prev.filter((x) => x.id !== id);
    });
  }

  function handleFileUpload(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const newSamples: RecordedSample[] = files.map((f) => ({
      id: `file-${Date.now()}-${Math.random()}`,
      blob: f,
      url: URL.createObjectURL(f),
      name: f.name,
    }));
    setSamples((prev) => [...prev, ...newSamples]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit() {
    if (!displayName.trim()) return;
    if (samples.length < 3) {
      setSubmitError("Please provide at least 3 voice samples.");
      return;
    }
    setSubmitError(null);
    setStep("submitting");

    try {
      const user = await registerUser({
        display_name: displayName.trim(),
        pitch_scale: preferences.pitch_scale,
        speaking_rate: preferences.speaking_rate,
        energy_scale: preferences.energy_scale,
        audio_samples: samples.map((sample) => ({
          blob: sample.blob,
          name: `${sample.name}.${sample.blob.type.includes("webm") ? "webm" : "wav"}`,
        })),
      });
      setStep("done");
      setTimeout(() => onSuccess(user), 900);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Registration failed");
      setStep("form");
    }
  }

  const canSubmit =
    displayName.trim().length > 0 && samples.length >= 3 && (step as string) === "form";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      {/* Backdrop */}
      <motion.div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={step !== "submitting" ? onClose : undefined}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 16 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-lg max-h-[90dvh] overflow-y-auto glass-elevated rounded-2xl ring-1 ring-white/[0.10] shadow-glass-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/[0.07]">
          <div>
            <h2 className="text-base font-semibold text-white">Register Voice Profile</h2>
            <p className="text-xs text-white/40 mt-0.5">
              Provide 3+ voice samples for speaker recognition
            </p>
          </div>
          {step !== "submitting" && (
            <button
              onClick={onClose}
              className="btn-ghost text-white/40 hover:text-white"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <div className="px-6 py-5 flex flex-col gap-5">
          {step === "done" ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center gap-3 py-8"
            >
              <div className="w-14 h-14 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
                <CheckCircle2 size={24} className="text-emerald-400" />
              </div>
              <p className="text-white font-semibold">Profile created!</p>
              <p className="text-xs text-white/40">Switching to your profile…</p>
            </motion.div>
          ) : (
            <>
              {/* Display name */}
              <div>
                <label className="block text-xs font-semibold text-white/40 uppercase tracking-[0.18em] mb-2">
                  Display name
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g. Alice"
                  className="input-glass text-sm"
                  disabled={step === "submitting"}
                />
              </div>

              {/* Voice samples */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-semibold text-white/40 uppercase tracking-[0.18em]">
                    Voice samples{" "}
                    <span
                      className={cn(
                        "font-normal normal-case tracking-normal ml-1",
                        samples.length >= 3
                          ? "text-emerald-400/70"
                          : "text-white/25"
                      )}
                    >
                      {samples.length}/3 min
                    </span>
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="btn-ghost text-xs py-1"
                      disabled={step === "submitting"}
                    >
                      <Upload size={11} /> Upload
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="audio/*"
                      multiple
                      className="sr-only"
                      onChange={handleFileUpload}
                    />
                    <button
                      type="button"
                      onClick={
                        recordingState === "idle"
                          ? startSampleRecording
                          : stopSampleRecording
                      }
                      disabled={step === "submitting"}
                      className={cn(
                        "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all duration-200",
                        recordingState === "recording"
                          ? "bg-red-500/20 text-red-300 border border-red-500/30"
                          : "bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30"
                      )}
                    >
                      {recordingState === "recording" ? (
                        <>
                          <MicOff size={11} /> Stop
                        </>
                      ) : (
                        <>
                          <Mic size={11} /> Record
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {samples.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-white/[0.10] px-4 py-6 text-center text-xs text-white/25">
                    Record or upload at least 3 voice samples (2–10 sec each)
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {samples.map((s) => (
                      <div
                        key={s.id}
                        className="flex items-center gap-3 rounded-xl bg-white/[0.04] border border-white/[0.07] px-3 py-2"
                      >
                        <audio
                          src={s.url}
                          controls
                          className="flex-1 h-7 min-w-0"
                          style={{ colorScheme: "dark" }}
                        />
                        <span className="text-[11px] text-white/35 truncate max-w-[80px] hidden sm:block">
                          {s.name}
                        </span>
                        <button
                          onClick={() => removeSample(s.id)}
                          className="text-white/25 hover:text-red-400 transition-colors ml-1 shrink-0"
                          disabled={step === "submitting"}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Error */}
              {submitError && (
                <div className="flex items-start gap-2 rounded-xl bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-xs text-red-300">
                  <XCircle size={13} className="shrink-0 mt-0.5" />
                  {submitError}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="btn-secondary text-sm py-2"
                  disabled={step === "submitting"}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!canSubmit || step === "submitting"}
                  className="btn-primary text-sm py-2"
                >
                  {step === "submitting" ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      Registering…
                    </>
                  ) : (
                    <>
                      <User size={14} />
                      Create profile
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
