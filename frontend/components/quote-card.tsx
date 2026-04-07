"use client";

import { motion, AnimatePresence } from "motion/react";
import { Pause, Play, Quote } from "lucide-react";
import { useRef, useState } from "react";
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

  function toggleAudio() {
    if (!resolvedAudioUrl) return;
    if (!audioRef.current) {
      audioRef.current = new Audio(resolvedAudioUrl);
      audioRef.current.onended = () => setPlaying(false);
      audioRef.current.onerror = () => setPlaying(false);
    }
    if (playing) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setPlaying(false);
    } else {
      audioRef.current.play().catch(() => setPlaying(false));
      setPlaying(true);
    }
  }

  if (variant === "primary") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        whileHover={{ scale: 1.005, transition: { duration: 0.2 } }}
        className={cn(
          "relative overflow-hidden rounded-2xl glass ring-1 ring-white/5 p-6 md:p-8",
          className
        )}
      >
        {/* Violet accent bar */}
        <span className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl accent-bar-violet" />

        {/* Top row */}
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
            {quote.relevance_score != null && (
              <span className="ml-1 text-[11px] text-violet-400/70 font-mono">
                {(quote.relevance_score * 100).toFixed(0)}%
              </span>
            )}
          </div>

          {resolvedAudioUrl && (
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={toggleAudio}
              className={cn(
                "flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-300",
                playing
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  : "bg-white/[0.07] text-white/60 hover:text-white hover:bg-white/[0.12] border border-white/[0.08]"
              )}
              aria-label={playing ? "Pause audio" : "Play audio"}
            >
              {playing ? <Pause size={12} /> : <Play size={12} />}
              {playing ? "Pause" : "Play"}
            </motion.button>
          )}
        </div>

        {/* Quote text */}
        <blockquote className="font-quote text-xl md:text-2xl leading-relaxed text-white/90 mb-5">
          &ldquo;{quote.quote_text}&rdquo;
        </blockquote>

        {/* Attribution */}
        <footer className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-sm font-semibold text-violet-300">
            {quote.author_name}
          </span>
          {quote.source_title && (
            <>
              <span className="text-white/25 text-xs">&mdash;</span>
              <span className="text-xs text-white/40 italic">
                {quote.source_title}
              </span>
            </>
          )}
        </footer>
      </motion.div>
    );
  }

  // Secondary (compact) variant
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{
        scale: 1.01,
        backgroundColor: "rgba(255,255,255,0.09)",
        transition: { duration: 0.2 },
      }}
      className={cn(
        "group relative overflow-hidden rounded-xl glass ring-1 ring-white/5 p-4 cursor-default",
        className
      )}
    >
      {/* Amber accent dot */}
      <span className="absolute left-0 top-0 bottom-0 w-0.5 rounded-l-xl accent-bar-amber opacity-70" />

      <p className="font-quote text-sm leading-relaxed text-white/75 line-clamp-3 mb-2.5">
        &ldquo;{quote.quote_text}&rdquo;
      </p>

      <footer className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="text-[11px] font-semibold text-amber-400/80">
          {quote.author_name}
        </span>
        {quote.source_title && (
          <span className="text-[11px] text-white/30 italic">
            · {quote.source_title}
          </span>
        )}
      </footer>
    </motion.div>
  );
}
