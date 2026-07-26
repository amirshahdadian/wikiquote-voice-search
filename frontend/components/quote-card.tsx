"use client";

import { Play, Quote, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { QuoteResult } from "@/lib/types";
import { resolveApiUrl } from "@/lib/api";

const cn = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(" ");

interface QuoteCardProps {
  quote: QuoteResult;
  variant?: "primary" | "secondary";
  audioUrl?: string | null;
  className?: string;
}

export default function QuoteCard({
  quote,
  variant = "secondary",
  audioUrl,
  className,
}: QuoteCardProps) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const resolvedAudioUrl = resolveApiUrl(audioUrl);

  useEffect(() => {
    if (!resolvedAudioUrl) return;
    const audio = new Audio(resolvedAudioUrl);
    audioRef.current = audio;
    audio.onended = () => {
      audio.currentTime = 0;
      setPlaying(false);
    };
    audio.onerror = () => setPlaying(false);
    audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));

    return () => {
      audio.pause();
      audio.currentTime = 0;
      if (audioRef.current === audio) audioRef.current = null;
    };
  }, [resolvedAudioUrl]);

  function stopAudio() {
    if (!audioRef.current) return;
    audioRef.current.pause();
    audioRef.current.currentTime = 0;
    setPlaying(false);
  }

  function toggleAudio() {
    if (!resolvedAudioUrl) return;
    if (!audioRef.current) {
      audioRef.current = new Audio(resolvedAudioUrl);
      audioRef.current.onended = () => {
        if (audioRef.current) audioRef.current.currentTime = 0;
        setPlaying(false);
      };
      audioRef.current.onerror = () => setPlaying(false);
    }
    if (playing) {
      stopAudio();
    } else {
      audioRef.current.play().catch(() => setPlaying(false));
      setPlaying(true);
    }
  }

  if (variant === "primary") {
    return (
      <div
        className={cn(
          "relative overflow-hidden rounded-2xl glass ring-1 ring-white/5 p-6 md:p-8 animate-[fade-up_0.4s_ease-out] transition-transform hover:scale-[1.005]",
          className
        )}
      >
        <span className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl accent-bar-violet" />

        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-2">
            <Quote
              size={16}
              className="text-violet-400 opacity-70 shrink-0 mt-0.5"
            />
            <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/40">
              {quote.search_type === "semantic"
                ? "Semantic match"
                : quote.search_type === "fulltext"
                ? "Full-text match"
                : "Best match"}
            </span>
          </div>

          {resolvedAudioUrl && (
            <button
              onClick={toggleAudio}
              className={cn(
                "flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-300 active:scale-90",
                playing
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  : "bg-white/[0.07] text-white/60 hover:text-white hover:bg-white/[0.12] border border-white/[0.08]"
              )}
              aria-label={playing ? "Stop audio" : "Play audio"}
            >
              {playing ? <Square size={12} /> : <Play size={12} />}
              {playing ? "Stop" : "Play"}
            </button>
          )}
        </div>

        <blockquote className="font-quote text-xl md:text-2xl leading-relaxed text-white/90 mb-5">
          &ldquo;{quote.quote_text}&rdquo;
        </blockquote>

        <footer className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {quote.author_name && (
            <span className="text-sm font-semibold text-violet-300">
              {quote.author_name}
            </span>
          )}
          {quote.source_title && (
            <>
              <span className="text-white/25 text-xs">&mdash;</span>
              <span className="text-xs text-white/40 italic">
                {quote.source_title}
              </span>
            </>
          )}
        </footer>
        <p className="mt-3 text-[11px] text-white/35">
          Wikiquote: {quote.page_title}
          {quote.citation ? ` · ${quote.citation}` : ""}
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl glass ring-1 ring-white/5 p-4 cursor-default animate-[fade-up_0.35s_ease-out] transition-all hover:scale-[1.01] hover:bg-white/[0.09]",
        className
      )}
    >
      <span className="absolute left-0 top-0 bottom-0 w-0.5 rounded-l-xl accent-bar-amber opacity-70" />

      <p className="font-quote text-sm leading-relaxed text-white/75 line-clamp-3 mb-2.5">
        &ldquo;{quote.quote_text}&rdquo;
      </p>

      <footer className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        {quote.author_name && (
          <span className="text-[11px] font-semibold text-amber-400/80">
            {quote.author_name}
          </span>
        )}
        {quote.source_title && (
          <span className="text-[11px] text-white/30 italic">
            · {quote.source_title}
          </span>
        )}
      </footer>
      <p className="mt-2 text-[10px] text-white/25">
        Wikiquote: {quote.page_title}
        {quote.citation ? ` · ${quote.citation}` : ""}
      </p>
    </div>
  );
}
