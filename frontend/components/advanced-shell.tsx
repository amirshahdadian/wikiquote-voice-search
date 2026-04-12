"use client";

import {
  BookOpen,
  Loader2,
  Mic,
  Search,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchAutocomplete,
  fetchIntelligentSearch,
  fetchPopularAuthors,
  fetchThemeQuotes,
  fetchVoiceSearch,
  submitVoiceQuery,
} from "@/lib/api";
import type { AuthorResult, QuoteResult } from "@/lib/types";

const cn = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(" ");

// ── Constants ──────────────────────────────────────────────────────────────────

const THEMES = [
  "love",
  "wisdom",
  "life",
  "success",
  "failure",
  "happiness",
  "peace",
  "war",
  "death",
  "friendship",
  "time",
  "freedom",
  "truth",
  "courage",
  "justice",
] as const;

type Theme = (typeof THEMES)[number];

// ── Small shared components ────────────────────────────────────────────────────

function SectionHeader({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex items-start gap-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-600/20 border border-violet-500/30">
        {icon}
      </div>
      <div>
        <h2 className="text-base font-semibold text-white/90">{title}</h2>
        <p className="mt-0.5 text-xs text-white/35 leading-relaxed">{subtitle}</p>
      </div>
    </div>
  );
}

function QuoteCard({ quote, compact = false }: { quote: QuoteResult; compact?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-2xl bg-white/[0.04] border border-white/[0.07] transition-colors hover:bg-white/[0.07]",
        compact ? "px-4 py-3" : "px-5 py-4"
      )}
    >
      <p
        className={cn(
          "font-serif italic leading-relaxed text-white/80",
          compact ? "text-sm" : "text-base"
        )}
      >
        &ldquo;{quote.quote_text}&rdquo;
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-white/40">{quote.author_name}</span>
        {quote.source_title && (
          <>
            <span className="text-white/15">·</span>
            <span className="text-xs text-white/25 truncate max-w-[18rem]">{quote.source_title}</span>
          </>
        )}
        {typeof quote.relevance_score === "number" && (
          <span className="ml-auto shrink-0 rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-300/70">
            {Math.round(quote.relevance_score * 100)}%
          </span>
        )}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center rounded-2xl border border-dashed border-white/[0.08] py-10">
      <p className="text-sm text-white/25">{text}</p>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <Loader2 size={20} className="text-violet-400/60 animate-spin" />
    </div>
  );
}

// ── Section: Theme Explorer ────────────────────────────────────────────────────

function ThemeExplorer() {
  const [activeTheme, setActiveTheme] = useState<Theme | null>(null);
  const [quotes, setQuotes] = useState<QuoteResult[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleThemeClick(theme: Theme) {
    if (activeTheme === theme) return;
    setActiveTheme(theme);
    setLoading(true);
    setQuotes([]);
    const results = await fetchThemeQuotes(theme, 10);
    setQuotes(results);
    setLoading(false);
  }

  return (
    <section className="rounded-3xl bg-white/[0.03] border border-white/[0.07] p-6 space-y-6">
      <SectionHeader
        icon={<BookOpen size={16} className="text-violet-400" />}
        title="Theme Explorer"
        subtitle="Browse quotes by curated theme. Each theme maps to a set of related keywords for wider recall."
      />

      <div className="flex flex-wrap gap-2">
        {THEMES.map((theme) => (
          <button
            key={theme}
            onClick={() => handleThemeClick(theme)}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm font-medium capitalize transition-all duration-200",
              activeTheme === theme
                ? "bg-violet-600/30 border border-violet-500/40 text-violet-200"
                : "bg-white/[0.05] border border-white/[0.08] text-white/50 hover:bg-violet-600/15 hover:border-violet-500/25 hover:text-white/80"
            )}
          >
            {theme}
          </button>
        ))}
      </div>

      {loading && <LoadingSpinner />}

      {!loading && activeTheme && quotes.length === 0 && (
        <EmptyState text={`No quotes found for "${activeTheme}".`} />
      )}

      {!loading && quotes.length > 0 && (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/25">
            {quotes.length} quotes — {activeTheme}
          </p>
          {quotes.map((q, i) => (
            <QuoteCard key={`${q.author_name}-${i}`} quote={q} />
          ))}
        </div>
      )}

      {!loading && !activeTheme && (
        <EmptyState text="Select a theme above to explore quotes." />
      )}
    </section>
  );
}

// ── Section: Popular Authors ───────────────────────────────────────────────────

function PopularAuthors({ initialAuthors }: { initialAuthors: AuthorResult[] }) {
  const [authors] = useState<AuthorResult[]>(initialAuthors);
  const [authorQuotes, setAuthorQuotes] = useState<QuoteResult[]>([]);
  const [activeAuthor, setActiveAuthor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleAuthorClick(name: string) {
    if (activeAuthor === name) {
      setActiveAuthor(null);
      setAuthorQuotes([]);
      return;
    }
    setActiveAuthor(name);
    setLoading(true);
    setAuthorQuotes([]);
    const results = await fetchIntelligentSearch(name, 6);
    setAuthorQuotes(results);
    setLoading(false);
  }

  const maxCount = authors[0]?.quote_count ?? 1;

  return (
    <section className="rounded-3xl bg-white/[0.03] border border-white/[0.07] p-6 space-y-6">
      <SectionHeader
        icon={<TrendingUp size={16} className="text-amber-400" />}
        title="Popular Authors"
        subtitle="Most-quoted authors in the knowledge graph, ranked by occurrence count. Click any author to preview their quotes."
      />

      {authors.length === 0 ? (
        <EmptyState text="No author data available." />
      ) : (
        <div className="space-y-2">
          {authors.map((author, i) => {
            const pct = Math.round((author.quote_count / maxCount) * 100);
            const isActive = activeAuthor === author.author_name;
            return (
              <div key={author.author_name}>
                <button
                  onClick={() => handleAuthorClick(author.author_name)}
                  className={cn(
                    "w-full rounded-2xl px-4 py-3 text-left transition-all duration-200",
                    "border",
                    isActive
                      ? "bg-amber-500/10 border-amber-500/25"
                      : "bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.06] hover:border-white/[0.10]"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <span className="w-5 text-right text-[11px] font-mono text-white/20 shrink-0">
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-3">
                        <span
                          className={cn(
                            "text-sm font-medium truncate",
                            isActive ? "text-amber-200" : "text-white/70"
                          )}
                        >
                          {author.author_name}
                        </span>
                        <span className="shrink-0 text-xs text-white/30 font-mono">
                          {author.quote_count.toLocaleString()}
                        </span>
                      </div>
                      <div className="mt-1.5 h-0.5 w-full rounded-full bg-white/[0.06]">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-500",
                            isActive ? "bg-amber-400/60" : "bg-violet-500/40"
                          )}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </button>

                {isActive && (
                  <div className="mt-2 ml-8 space-y-2">
                    {loading && <LoadingSpinner />}
                    {!loading && authorQuotes.length === 0 && (
                      <EmptyState text="No quotes found for this author." />
                    )}
                    {!loading &&
                      authorQuotes.map((q, j) => (
                        <QuoteCard key={`${q.source_title}-${j}`} quote={q} compact />
                      ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ── Section: Intelligent Search ────────────────────────────────────────────────

function IntelligentSearchSection() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<QuoteResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    const res = await fetchIntelligentSearch(query.trim(), 12);
    setResults(res);
    setLoading(false);
  }

  return (
    <section className="rounded-3xl bg-white/[0.03] border border-white/[0.07] p-6 space-y-6">
      <SectionHeader
        icon={<Sparkles size={16} className="text-emerald-400" />}
        title="Intelligent Search"
        subtitle="Full fuzzy search across the graph — higher recall than the standard search, including near-miss and phonetic variants."
      />

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          className={cn(
            "flex-1 rounded-2xl bg-white/[0.06] border border-white/[0.08] px-5 py-3 text-sm text-white",
            "placeholder:text-white/25 outline-none",
            "focus:border-violet-500/50 focus:bg-white/[0.09] transition-all duration-200"
          )}
          placeholder={'Search with fuzzy matching, e.g. "to be or not to be"'}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className={cn(
            "flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all duration-200",
            "bg-violet-600 hover:bg-violet-500 text-white",
            "disabled:opacity-40 disabled:cursor-not-allowed"
          )}
        >
          {loading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Search size={14} />
          )}
          Search
        </button>
      </form>

      {loading && <LoadingSpinner />}

      {!loading && searched && results.length === 0 && (
        <EmptyState text="No matches found. Try a shorter fragment or different keywords." />
      )}

      {!loading && results.length > 0 && (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/25">
            {results.length} results
          </p>
          {results.map((q, i) => (
            <QuoteCard key={`${q.author_name}-${i}`} quote={q} />
          ))}
        </div>
      )}

      {!loading && !searched && (
        <EmptyState text="Enter a query above to run an intelligent search." />
      )}
    </section>
  );
}

// ── Section: Autocomplete ──────────────────────────────────────────────────────

function AutocompleteSection() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<QuoteResult[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSuggestions = useCallback(async (value: string) => {
    if (!value.trim()) {
      setSuggestions([]);
      return;
    }
    setLoading(true);
    const res = await fetchAutocomplete(value.trim(), 5);
    setSuggestions(res);
    setLoading(false);
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 320);
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return (
    <section className="rounded-3xl bg-white/[0.03] border border-white/[0.07] p-6 space-y-6">
      <SectionHeader
        icon={<Search size={16} className="text-cyan-400" />}
        title="Live Autocomplete"
        subtitle="Exact-match suggestions as you type — no fuzzy expansion, so results are fast and precise."
      />

      <div className="relative">
        <input
          className={cn(
            "w-full rounded-2xl bg-white/[0.06] border border-white/[0.08] px-5 py-3 text-sm text-white",
            "placeholder:text-white/25 outline-none pr-10",
            "focus:border-cyan-500/50 focus:bg-white/[0.09] transition-all duration-200"
          )}
          placeholder="Start typing a quote fragment…"
          value={query}
          onChange={handleChange}
        />
        {loading && (
          <Loader2
            size={14}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 animate-spin"
          />
        )}
      </div>

      {!loading && query.trim() && suggestions.length === 0 && (
        <EmptyState text="No exact matches yet — keep typing." />
      )}

      {suggestions.length > 0 && (
        <div className="space-y-2">
          {suggestions.map((q, i) => (
            <QuoteCard key={`${q.author_name}-${i}`} quote={q} compact />
          ))}
        </div>
      )}

      {!query.trim() && (
        <EmptyState text="Type above to get live quote suggestions." />
      )}
    </section>
  );
}

// ── Section: Voice-Optimised Search ───────────────────────────────────────────

function VoiceSearchSection() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<QuoteResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "processing">("idle");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    const res = await fetchVoiceSearch(query.trim(), 3);
    setResults(res);
    setLoading(false);
  }

  async function startRecording() {
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
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setVoiceState("processing");
        const blob = new Blob(chunksRef.current, { type: mimeType });
        try {
          const payload = await submitVoiceQuery({
            audio: blob,
            filename: "recording.webm",
          });
          const transcript: string = payload.normalized_transcript ?? payload.transcript ?? "";
          setQuery(transcript);
          if (transcript) {
            setLoading(true);
            setSearched(true);
            const voiceRes = await fetchVoiceSearch(transcript, 3);
            setResults(voiceRes);
            setLoading(false);
          }
        } catch {
          // voice transcription unavailable; user can type manually
        }
        setVoiceState("idle");
      };
      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setVoiceState("recording");
    } catch {
      setVoiceState("idle");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
  }

  return (
    <section className="rounded-3xl bg-white/[0.03] border border-white/[0.07] p-6 space-y-6">
      <SectionHeader
        icon={<Mic size={16} className="text-rose-400" />}
        title="Voice-Optimised Search"
        subtitle="Returns up to 3 concise results with quotes truncated to 200 characters — ideal for text-to-speech playback."
      />

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          className={cn(
            "flex-1 rounded-2xl bg-white/[0.06] border border-white/[0.08] px-5 py-3 text-sm text-white",
            "placeholder:text-white/25 outline-none",
            "focus:border-rose-500/50 focus:bg-white/[0.09] transition-all duration-200"
          )}
          placeholder="Spoken query or text equivalent…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="button"
          onClick={voiceState === "recording" ? stopRecording : startRecording}
          disabled={voiceState === "processing"}
          className={cn(
            "flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition-all duration-200",
            voiceState === "recording"
              ? "bg-red-600/80 hover:bg-red-500/80 border border-red-500/40 text-white"
              : "bg-white/[0.07] hover:bg-white/[0.11] border border-white/[0.10] text-white/70 hover:text-white",
            voiceState === "processing" && "opacity-50 cursor-not-allowed"
          )}
          title={voiceState === "recording" ? "Stop recording" : "Record voice query"}
        >
          {voiceState === "processing" ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Mic size={14} className={voiceState === "recording" ? "text-white" : ""} />
          )}
          <span className="hidden sm:inline">
            {voiceState === "recording"
              ? "Stop"
              : voiceState === "processing"
              ? "Processing…"
              : "Record"}
          </span>
        </button>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className={cn(
            "flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all duration-200",
            "bg-rose-600/80 hover:bg-rose-500/80 text-white",
            "disabled:opacity-40 disabled:cursor-not-allowed"
          )}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
          Search
        </button>
      </form>

      {voiceState === "recording" && (
        <p className="text-center text-xs text-red-400/80 animate-pulse">
          Recording… click Stop when done
        </p>
      )}

      {loading && <LoadingSpinner />}

      {!loading && searched && results.length === 0 && (
        <EmptyState text="No matches found. Try rephrasing." />
      )}

      {!loading && results.length > 0 && (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/25">
            {results.length} voice-ready result{results.length !== 1 ? "s" : ""}
          </p>
          {results.map((q, i) => (
            <QuoteCard key={`${q.author_name}-${i}`} quote={q} />
          ))}
        </div>
      )}

      {!loading && !searched && (
        <EmptyState text="Record a voice query or type text above." />
      )}
    </section>
  );
}

// ── Root shell ─────────────────────────────────────────────────────────────────

export default function AdvancedShell({
  initialAuthors,
}: {
  initialAuthors: AuthorResult[];
}) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      {/* Header */}
      <header className="flex-none flex items-center justify-between border-b border-white/[0.06] px-6 py-3 bg-white/[0.02] backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2.5 group"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-600/20 border border-violet-500/30">
              <BookOpen size={14} className="text-violet-400" />
            </div>
            <div className="leading-none">
              <span className="text-sm font-semibold tracking-tight text-white/90">
                WikiQuote{" "}
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-violet-300 font-bold">
                  Voice
                </span>
              </span>
            </div>
          </Link>

          <span className="hidden sm:block text-white/15">·</span>

          <span className="hidden sm:flex items-center gap-1.5 rounded-full bg-violet-500/15 border border-violet-500/25 px-3 py-1 text-[11px] font-semibold text-violet-300/80 uppercase tracking-wider">
            <Sparkles size={10} />
            Advanced Features
          </span>
        </div>

        <nav className="flex items-center gap-2">
          <Link
            href="/"
            className="rounded-xl px-4 py-1.5 text-sm text-white/50 hover:text-white hover:bg-white/[0.07] transition-all duration-200"
          >
            Home
          </Link>
          <Link
            href="/users"
            className="flex items-center gap-1.5 rounded-xl px-4 py-1.5 text-sm text-white/50 hover:text-white hover:bg-white/[0.07] transition-all duration-200"
          >
            <Users size={13} />
            Users
          </Link>
        </nav>
      </header>

      {/* Scrollable content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 py-8 md:px-8 space-y-6">

          {/* Page heading */}
          <div className="mb-2">
            <h1 className="text-2xl font-bold tracking-tight text-white/90">
              Advanced Features
            </h1>
            <p className="mt-1.5 text-sm text-white/35 leading-relaxed max-w-2xl">
              Deeper tools built on top of the quote knowledge graph — browse by theme, explore popular
              authors, run fuzzy searches, get live autocomplete suggestions, and test voice-optimised
              results.
            </p>
          </div>

          {/* Two-column grid on wide screens */}
          <div className="grid gap-6 lg:grid-cols-2">
            <ThemeExplorer />
            <PopularAuthors initialAuthors={initialAuthors} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <IntelligentSearchSection />
            <AutocompleteSection />
          </div>

          <VoiceSearchSection />
        </div>
      </main>
    </div>
  );
}
