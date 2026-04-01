"use client";

import { useEffect, useState } from "react";

import { resolveApiUrl } from "@/lib/api";
import { ChatQueryResponse, QuoteResult, VoiceQueryResponse } from "@/lib/types";

type QuoteResponseCardProps = {
  response: ChatQueryResponse | VoiceQueryResponse | null;
};

const warningLabels: Record<string, string> = {
  low_asr_confidence: "ASR confidence was low. Try speaking closer to the microphone or uploading a clearer clip.",
  multiple_close_matches: "Several close quote matches were found. You can inspect the alternatives below.",
  speaker_not_recognized: "Speaker recognition did not find a confident match. You can retry or choose a profile manually.",
  no_quote_found: "No exact quote match was found. The response uses the closest available result or asks for a rephrase.",
  tts_fallback: "Primary TTS failed, so the backend used the simpler speech fallback.",
  tts_unavailable: "Audio playback could not be generated for this response.",
  no_additional_matches: "There was no stronger alternative left from the previous search.",
  selected_user_not_found: "The selected profile was not found on the backend.",
};

export default function QuoteResponseCard({ response }: QuoteResponseCardProps) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    setActiveIndex(0);
  }, [response]);

  if (!response) {
    return (
      <div className="editorial-card flex min-h-[42rem] flex-col">
        <p className="kicker">Response</p>
        <p className="mt-4 max-w-xl text-sm leading-7 text-scholarly-muted">
          Your latest quote answer, transcript, alternatives, and generated audio will appear here.
        </p>
        <div className="mt-8 grid flex-1 place-items-center rounded-[1.75rem] border border-dashed border-scholarly-line/40 bg-scholarly-low">
          <div className="max-w-md px-6 text-center">
            <p className="text-lg font-medium text-ink">Start with a prompt</p>
            <p className="mt-3 text-sm leading-7 text-scholarly-muted">
              Record a voice query or type a quote fragment on the left. The selected result, transcript, and audio playback
              will appear here.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const candidates: QuoteResult[] = response.best_quote
    ? [response.best_quote, ...response.related_quotes]
    : response.related_quotes;
  const activeQuote = candidates[activeIndex] ?? response.best_quote ?? null;
  const audioUrl = resolveApiUrl(response.audio_url);

  return (
    <div className="editorial-card flex min-h-[42rem] flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-3">
        <span className="status-pill">{response.intent_type.replaceAll("_", " ")}</span>
        {response.recognized_user ? (
          <span className="status-pill">
            {response.recognized_user.display_name}
            {typeof response.recognized_user.confidence === "number"
              ? ` · ${(response.recognized_user.confidence * 100).toFixed(1)}%`
              : ""}
          </span>
        ) : null}
      </div>

      <p className="mt-6 max-w-4xl text-xl leading-9 text-ink">{response.response_text}</p>

      {"transcript" in response ? (
        <div className="mt-5 rounded-xl bg-scholarly-low p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-scholarly-muted">Transcript</p>
          <p className="mt-2 text-sm text-ink">{response.transcript}</p>
        </div>
      ) : null}

      {activeQuote ? (
        <div className="mt-6 rounded-2xl bg-scholarly-low p-6">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-scholarly-tertiary px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-[#445269]">
              {activeQuote.relevance_score ? `${Math.round(activeQuote.relevance_score * 100)}% match` : "Selected quote"}
            </span>
            <div className="h-px flex-1 bg-scholarly-line/20" />
          </div>
          <blockquote className="mt-4 text-2xl leading-10 text-ink">“{activeQuote.quote_text}”</blockquote>
          <p className="mt-4 text-sm text-scholarly-muted">
            {activeQuote.author_name} · {activeQuote.source_title}
          </p>
        </div>
      ) : null}

      {candidates.length > 1 ? (
        <div className="mt-6">
          <p className="text-xs uppercase tracking-[0.18em] text-scholarly-muted">Alternative matches</p>
          <div className="mt-3 flex flex-wrap gap-3">
            {candidates.map((quote, index) => (
              <button
                className={index === activeIndex ? "primary-button" : "secondary-button"}
                key={`${quote.author_name}-${quote.source_title}-${index}`}
                onClick={() => setActiveIndex(index)}
                type="button"
              >
                {index === 0 ? "Best Match" : `Alternative ${index}`}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {audioUrl ? (
        <div className="mt-6 rounded-full bg-scholarly-low px-4 py-3">
          <audio className="w-full" controls src={audioUrl} />
        </div>
      ) : null}

      <div className="mt-auto pt-6">
        {response.warnings.length > 0 ? (
          <div className="space-y-2">
            {response.warnings.map((warning) => (
              <div className="notice-warning" key={warning}>
                {warningLabels[warning] ?? warning.replaceAll("_", " ")}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
