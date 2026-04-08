"use client";

import { AnimatePresence, motion } from "motion/react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Mic,
  MicOff,
  Plus,
  Quote,
  RefreshCw,
  Search,
  Send,
  Settings,
  Trash2,
  Upload,
  User,
  Users,
  WifiOff,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type {
  ChatQueryResponse,
  QuoteResult,
  UserPreferences,
  UserProfile,
  VoiceQueryResponse,
} from "@/lib/types";
import { getApiBaseUrl, resolveApiUrl } from "@/lib/api";
import QuoteCard from "@/components/quote-card";
import VoiceWaveform from "@/components/voice-waveform";

const cn = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(" ");

// ── Types ─────────────────────────────────────────────────────────────────────

type VoiceState = "idle" | "listening" | "processing";

interface HealthStatus {
  search: boolean;
  asr: boolean;
  speaker_id: boolean;
  tts: boolean;
  sqlite: boolean;
}

interface RecordedSample {
  id: string;
  blob: Blob;
  url: string;
  name: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const EXAMPLE_QUERIES = [
  "Something about courage",
  "Einstein on imagination",
  "Churchill wartime speech",
  "Twain on truth",
];

const FOLLOWUP_CHIPS = [
  { label: "Another one", prompt: "Give me another quote like that" },
  { label: "Who said that?", prompt: "Tell me more about who said that" },
  { label: "More context", prompt: "Give me more context about this quote" },
  { label: "Repeat", prompt: "__repeat__" },
];

// ── Main component ─────────────────────────────────────────────────────────────

interface MainShellProps {
  initialUsers: UserProfile[];
  initialQuote: QuoteResult | null;
}

export default function MainShell({ initialUsers, initialQuote }: MainShellProps) {
  // Search / chat state
  const [query, setQuery] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [selectedUserId, setSelectedUserId] = useState<string | undefined>();
  const [response, setResponse] = useState<
    ChatQueryResponse | VoiceQueryResponse | null
  >(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Misc refs
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const userDropdownRef = useRef<HTMLDivElement>(null);

  const apiBase = getApiBaseUrl();

  // ── Health poll ────────────────────────────────────────────────────────────

  useEffect(() => {
    async function checkHealth() {
      try {
        const res = await fetch(`${apiBase}/api/health`);
        if (res.ok) setHealth(await res.json());
      } catch {
        /* silently ignore */
      }
    }
    checkHealth();
    const id = setInterval(checkHealth, 30_000);
    return () => clearInterval(id);
  }, [apiBase]);

  // Close dropdown on outside click
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

  // ── Text query ─────────────────────────────────────────────────────────────

  async function sendTextQuery(message: string) {
    if (!message.trim() || isLoading) return;
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${apiBase}/api/chat/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
          selected_user_id: selectedUserId,
        }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data: ChatQueryResponse = await res.json();
      setResponse(data);
      setConversationId(data.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }

  function handleSearch(e?: FormEvent) {
    e?.preventDefault();
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
      setError("Microphone access denied. Please allow microphone permissions.");
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && voiceState === "listening") {
      mediaRecorderRef.current.stop();
    }
  }

  function handleVoiceButtonClick() {
    if (voiceState === "idle") {
      startRecording();
    } else if (voiceState === "listening") {
      stopRecording();
    }
  }

  async function sendVoiceQuery(blob: Blob, mimeType: string) {
    setError(null);
    try {
      const ext = mimeType.includes("webm") ? "webm" : "ogg";
      const formData = new FormData();
      formData.append("audio", blob, `recording.${ext}`);
      if (conversationId) formData.append("conversation_id", conversationId);
      if (selectedUserId) formData.append("selected_user_id", selectedUserId);

      const res = await fetch(`${apiBase}/api/voice/query`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data: VoiceQueryResponse = await res.json();
      setResponse(data);
      setConversationId(data.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice query failed");
    } finally {
      setVoiceState("idle");
    }
  }

  // ── Follow-up chips ────────────────────────────────────────────────────────

  function handleFollowUp(prompt: string) {
    if (prompt === "__repeat__") {
      if (response?.audio_url) {
        const audio = new Audio(resolveApiUrl(response.audio_url) ?? "");
        audio.play().catch(() => {});
      }
      return;
    }
    sendTextQuery(prompt);
  }

  // ── Selected user label ────────────────────────────────────────────────────

  const selectedUser = users.find((u) => u.user_id === selectedUserId);

  // ── Health dots ────────────────────────────────────────────────────────────

  function HealthDots() {
    if (!health) return null;
    const services: [string, boolean][] = [
      ["Search", health.search],
      ["ASR", health.asr],
      ["TTS", health.tts],
      ["ID", health.speaker_id],
      ["DB", health.sqlite],
    ];
    return (
      <div className="flex items-center gap-1.5">
        {services.map(([label, ok]) => (
          <div key={label} className="flex items-center gap-1 group relative">
            <span
              className={cn(
                "status-dot",
                ok ? "status-dot-online" : "status-dot-offline"
              )}
            />
            <span className="text-[10px] text-white/30 group-hover:text-white/50 transition-colors hidden sm:block">
              {label}
            </span>
          </div>
        ))}
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="relative h-dvh w-full flex flex-col overflow-hidden">
      {/* ── Header ── */}
      <header className="flex-none flex items-center justify-between px-5 md:px-8 py-4 border-b border-white/[0.06] glass-elevated z-20">
        {/* Logo + name */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-violet-600/20 border border-violet-500/30">
            <Quote size={14} className="text-violet-400" />
          </div>
          <span className="text-sm font-semibold tracking-tight text-white/90">
            WikiQuote{" "}
            <span className="gradient-text-violet font-bold">Voice</span>
          </span>
        </div>

        {/* Right side controls */}
        <div className="flex items-center gap-3">
          <HealthDots />

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

          {/* Manage users link */}
          <Link
            href="/users"
            className="btn-secondary py-1.5 px-3 text-xs"
            title="Manage enrolled users"
          >
            <Users size={13} />
            <span className="hidden sm:block">Users</span>
          </Link>

          {/* Add user button */}
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

      {/* ── Body ── */}
      <main className="flex-1 overflow-hidden flex flex-col items-center px-4 md:px-8 pt-8 pb-4 gap-6 min-h-0">
        {/* ── Hero ── */}
        <div className="text-center flex-none">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-2"
          >
            <span className="gradient-text">Find Any Quote</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
            className="text-white/40 text-sm md:text-base max-w-md mx-auto"
          >
            Search Wikiquote by voice or text · Speaker-aware · Personalized TTS
          </motion.p>
        </div>

        {/* ── Search area ── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-2xl flex-none"
        >
          <form onSubmit={handleSearch} className="relative">
            <div className="relative group">
              <Search
                size={16}
                className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30 group-focus-within:text-violet-400 transition-colors duration-300 pointer-events-none"
              />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about quotes…"
                className="input-glass pl-10 pr-16"
                disabled={isLoading || voiceState !== "idle"}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="submit"
                disabled={!query.trim() || isLoading || voiceState !== "idle"}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-30 disabled:cursor-not-allowed text-white transition-all duration-200"
                aria-label="Search"
              >
                {isLoading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Send size={14} />
                )}
              </button>
            </div>
          </form>

          {/* Voice button */}
          <div className="flex flex-col items-center mt-5 gap-3">
            <div className="relative flex items-center justify-center">
              {/* Pulse rings when listening */}
              {voiceState === "listening" && (
                <>
                  <span className="absolute inset-0 rounded-full bg-red-500/30 animate-[pulse-ring_1.8s_ease-out_infinite]" />
                  <span className="absolute inset-0 rounded-full bg-red-500/15 animate-[pulse-ring_1.8s_ease-out_0.6s_infinite]" />
                </>
              )}

              <motion.button
                whileTap={{ scale: 0.92 }}
                whileHover={{ scale: voiceState === "idle" ? 1.06 : 1 }}
                onClick={handleVoiceButtonClick}
                disabled={voiceState === "processing" || isLoading}
                className={cn(
                  "relative z-10 flex items-center justify-center w-14 h-14 rounded-full transition-all duration-300",
                  "shadow-glass ring-1",
                  voiceState === "idle" &&
                    "bg-white/[0.08] hover:bg-violet-600/30 ring-white/[0.12] hover:ring-violet-500/40 hover:shadow-glow-sm",
                  voiceState === "listening" &&
                    "bg-red-600/80 ring-red-500/50 shadow-[0_0_24px_rgba(239,68,68,0.4)]",
                  voiceState === "processing" &&
                    "bg-white/[0.06] ring-white/10 cursor-wait"
                )}
                aria-label={
                  voiceState === "idle"
                    ? "Start recording"
                    : voiceState === "listening"
                    ? "Stop recording"
                    : "Processing..."
                }
              >
                {voiceState === "idle" && (
                  <Mic size={20} className="text-white/70" />
                )}
                {voiceState === "listening" && (
                  <VoiceWaveform active amplitude={1.2} />
                )}
                {voiceState === "processing" && (
                  <Loader2 size={18} className="text-white/60 animate-spin" />
                )}
              </motion.button>
            </div>

            <span className="text-[11px] text-white/30 font-medium">
              {voiceState === "idle" && "Hold to record · Click to start"}
              {voiceState === "listening" && (
                <span className="text-red-400/80">Recording — click to stop</span>
              )}
              {voiceState === "processing" && (
                <span className="text-violet-400/80">Processing voice…</span>
              )}
            </span>
          </div>
        </motion.div>

        {/* ── Results / idle area ── */}
        <div
          ref={resultsRef}
          className="flex-1 w-full max-w-2xl overflow-y-auto min-h-0 pr-0.5"
        >
          <AnimatePresence mode="wait">
            {/* Error */}
            {error && (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-start gap-3 rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 mb-4 text-sm text-red-300"
              >
                <XCircle size={15} className="shrink-0 mt-0.5 text-red-400" />
                <div className="flex-1">{error}</div>
                <button
                  onClick={() => setError(null)}
                  className="text-red-400/60 hover:text-red-300 transition-colors"
                >
                  <X size={13} />
                </button>
              </motion.div>
            )}

            {/* Warnings from response */}
            {response?.warnings?.length ? (
              <motion.div
                key="warnings"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-start gap-3 rounded-xl bg-amber-500/10 border border-amber-500/20 px-4 py-3 mb-4 text-sm text-amber-200/80"
              >
                <AlertTriangle
                  size={15}
                  className="shrink-0 mt-0.5 text-amber-400"
                />
                <div className="flex-1 flex flex-col gap-1">
                  {response.warnings.map((w, i) => (
                    <span key={i}>{w}</span>
                  ))}
                </div>
              </motion.div>
            ) : null}

            {/* Active response */}
            {response ? (
              <motion.div
                key={response.conversation_id + (response as VoiceQueryResponse).transcript}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col gap-3"
              >
                {/* Recognized user / transcript chip */}
                {(response as VoiceQueryResponse).transcript && (
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 bg-white/[0.06] border border-white/[0.08] text-xs text-white/50">
                      <Mic size={10} className="text-violet-400" />
                      &ldquo;{(response as VoiceQueryResponse).transcript}&rdquo;
                    </span>
                    {response.recognized_user && (
                      <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300/80">
                        <CheckCircle2 size={10} />
                        {response.recognized_user.display_name}
                      </span>
                    )}
                  </div>
                )}

                {/* Response text */}
                {response.response_text && (
                  <p className="text-sm text-white/60 leading-relaxed px-1">
                    {response.response_text}
                  </p>
                )}

                {/* Primary quote */}
                {response.best_quote && (
                  <QuoteCard
                    quote={response.best_quote}
                    variant="primary"
                    audioUrl={response.audio_url}
                  />
                )}

                {/* Related quotes */}
                {response.related_quotes?.length > 0 && (
                  <div className="flex flex-col gap-2 mt-1">
                    <span className="text-[11px] text-white/30 font-semibold uppercase tracking-[0.2em] px-1">
                      Related
                    </span>
                    {response.related_quotes.slice(0, 3).map((q, i) => (
                      <QuoteCard key={i} quote={q} variant="secondary" />
                    ))}
                  </div>
                )}

                {/* No quote found */}
                {!response.best_quote && !response.related_quotes?.length && (
                  <div className="rounded-xl glass ring-1 ring-white/5 px-5 py-4 text-sm text-white/50 text-center">
                    No matching quotes found. Try a different phrasing.
                  </div>
                )}

                {/* Follow-up chips */}
                <div className="flex flex-wrap gap-2 mt-1 pb-1">
                  {FOLLOWUP_CHIPS.map((chip) => (
                    <button
                      key={chip.label}
                      onClick={() => handleFollowUp(chip.prompt)}
                      disabled={isLoading}
                      className={cn(
                        "rounded-full px-3 py-1 text-xs font-medium transition-all duration-200",
                        "bg-white/[0.06] hover:bg-white/[0.11] border border-white/[0.08] hover:border-white/[0.16]",
                        "text-white/50 hover:text-white/90",
                        "disabled:opacity-40 disabled:cursor-not-allowed"
                      )}
                    >
                      {chip.label}
                    </button>
                  ))}
                  <button
                    onClick={() => {
                      setResponse(null);
                      setConversationId(undefined);
                      setError(null);
                    }}
                    className="rounded-full px-3 py-1 text-xs font-medium text-white/30 hover:text-white/60 transition-colors duration-200 flex items-center gap-1"
                  >
                    <X size={10} /> Clear
                  </button>
                </div>
              </motion.div>
            ) : (
              /* Idle state — random quote + example pills */
              <motion.div
                key="idle"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex flex-col gap-4"
              >
                {initialQuote && (
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] text-white/25 font-semibold uppercase tracking-[0.2em] px-1">
                      Quote of the moment
                    </span>
                    <QuoteCard quote={initialQuote} variant="primary" />
                  </div>
                )}

                <div className="flex flex-col gap-2">
                  <span className="text-[11px] text-white/25 font-semibold uppercase tracking-[0.2em] px-1">
                    Try asking
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {EXAMPLE_QUERIES.map((q) => (
                      <button
                        key={q}
                        onClick={() => {
                          sendTextQuery(q);
                        }}
                        className={cn(
                          "rounded-full px-3.5 py-1.5 text-xs font-medium transition-all duration-200",
                          "bg-white/[0.05] hover:bg-violet-600/20 border border-white/[0.07] hover:border-violet-500/30",
                          "text-white/45 hover:text-white/90"
                        )}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* ── Register modal ── */}
      <AnimatePresence>
        {showRegister && (
          <RegisterModal
            apiBase={apiBase}
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
  apiBase: string;
  onClose: () => void;
  onSuccess: (user: UserProfile) => void;
}

type RegisterStep = "form" | "recording" | "submitting" | "done";

function RegisterModal({ apiBase, onClose, onSuccess }: RegisterModalProps) {
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
      const fd = new FormData();
      fd.append("display_name", displayName.trim());
      fd.append("pitch_scale", String(preferences.pitch_scale));
      fd.append("speaking_rate", String(preferences.speaking_rate));
      fd.append("energy_scale", String(preferences.energy_scale));
      if (preferences.style) fd.append("style", preferences.style);
      samples.forEach((s) => {
        const ext = s.blob.type.includes("webm") ? "webm" : "wav";
        fd.append("audio_samples", s.blob, `${s.name}.${ext}`);
      });

      const res = await fetch(`${apiBase}/api/users/register`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Server error ${res.status}`);
      }
      const user: UserProfile = await res.json();
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

              {/* Voice preferences */}
              <div className="grid grid-cols-2 gap-3">
                {(
                  [
                    ["Pitch", "pitch_scale", 0.5, 2.0],
                    ["Speed", "speaking_rate", 0.5, 2.0],
                    ["Energy", "energy_scale", 0.5, 2.0],
                  ] as [string, keyof UserPreferences, number, number][]
                ).map(([label, key, min, max]) => (
                  <div key={key}>
                    <label className="block text-xs font-semibold text-white/40 uppercase tracking-[0.15em] mb-1.5">
                      {label}{" "}
                      <span className="text-white/25 normal-case tracking-normal font-normal">
                        {Number(preferences[key]).toFixed(1)}×
                      </span>
                    </label>
                    <input
                      type="range"
                      min={min}
                      max={max}
                      step={0.1}
                      value={Number(preferences[key])}
                      onChange={(e) =>
                        setPreferences((p) => ({
                          ...p,
                          [key]: parseFloat(e.target.value),
                        }))
                      }
                      className="w-full accent-violet-500"
                      disabled={step === "submitting"}
                    />
                  </div>
                ))}
                <div>
                  <label className="block text-xs font-semibold text-white/40 uppercase tracking-[0.15em] mb-1.5">
                    Style
                  </label>
                  <input
                    type="text"
                    value={preferences.style ?? ""}
                    onChange={(e) =>
                      setPreferences((p) => ({ ...p, style: e.target.value }))
                    }
                    placeholder="neutral"
                    className="input-glass text-sm py-2"
                    disabled={step === "submitting"}
                  />
                </div>
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
