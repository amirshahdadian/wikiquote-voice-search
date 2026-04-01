"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import AudioRecorder from "@/components/audio-recorder";
import QuoteResponseCard from "@/components/quote-response-card";
import { getApiBaseUrl } from "@/lib/api";
import { ChatQueryResponse, LocalAudioSample, UserProfile, VoiceQueryResponse } from "@/lib/types";

type HistoryEntry = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type InteractionShellProps = {
  initialUsers: UserProfile[];
};

function nextEntryId() {
  return globalThis.crypto?.randomUUID?.() ?? `history-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function InteractionShell({ initialUsers }: InteractionShellProps) {
  const searchParams = useSearchParams();
  const [selectedUserId, setSelectedUserId] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [latestResponse, setLatestResponse] = useState<ChatQueryResponse | VoiceQueryResponse | null>(null);
  const [statusText, setStatusText] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [permissionWarning, setPermissionWarning] = useState<string | null>(null);

  useEffect(() => {
    const initialUser = searchParams.get("user");
    if (initialUser) {
      setSelectedUserId(initialUser);
    }
  }, [searchParams]);

  function updateConversation(userText: string, response: ChatQueryResponse | VoiceQueryResponse) {
    setConversationId(response.conversation_id);
    setLatestResponse(response);
    setHistory((current) => {
      const next: HistoryEntry[] = [
        ...current,
        { id: nextEntryId(), role: "user", content: userText },
        { id: nextEntryId(), role: "assistant", content: response.response_text },
      ];
      return next.slice(-8);
    });
  }

  async function sendTextQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!message.trim()) {
      return;
    }

    setStatusText("Searching the graph and generating a response...");

    try {
      const response = await fetch(`${getApiBaseUrl()}/api/chat/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: message.trim(),
          conversation_id: conversationId ?? undefined,
          selected_user_id: selectedUserId || undefined,
        }),
      });

      const payload = (await response.json()) as ChatQueryResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Text query failed." : "Text query failed.");
      }

      updateConversation(message.trim(), payload as ChatQueryResponse);
      setMessage("");
      setStatusText("Ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Text query failed.");
      setStatusText("Ready");
    }
  }

  async function sendVoiceQuery(sample: LocalAudioSample) {
    setError(null);
    setStatusText("Transcribing, recognizing the speaker, searching, and generating audio...");

    try {
      const formData = new FormData();
      formData.append("audio", sample.blob, sample.name);
      if (conversationId) {
        formData.append("conversation_id", conversationId);
      }
      if (selectedUserId) {
        formData.append("selected_user_id", selectedUserId);
      }

      const response = await fetch(`${getApiBaseUrl()}/api/voice/query`, {
        method: "POST",
        body: formData,
      });

      const payload = (await response.json()) as VoiceQueryResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Voice query failed." : "Voice query failed.");
      }

      updateConversation((payload as VoiceQueryResponse).transcript, payload as VoiceQueryResponse);
      setStatusText("Ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Voice query failed.");
      setStatusText("Ready");
    }
  }

  function clearConversation() {
    setConversationId(null);
    setHistory([]);
    setLatestResponse(null);
    setMessage("");
    setError(null);
    setStatusText("Ready");
  }

  return (
    <div className="page-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="flex items-center gap-8">
            <Link className="brand" href="/">
              Which Quote?
            </Link>
            <nav className="hidden items-center gap-6 md:flex">
              <Link className="nav-link-active" href="/app">
                Dashboard
              </Link>
              <Link className="nav-link" href="/">
                Discover
              </Link>
              <Link className="nav-link" href="/profile">
                Profile
              </Link>
            </nav>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link className="secondary-button" href="/">
              Home
            </Link>
            <Link className="secondary-button" href="/profile">
              Profile Settings
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[100rem] gap-10 px-6 pb-16 pt-10 lg:grid-cols-12 lg:px-10">
        <aside className="space-y-8 lg:col-span-3 lg:order-1 order-2">
          <div className="editorial-card">
            <h3 className="text-sm font-bold uppercase tracking-[0.22em] text-scholarly-muted">Recent Inquiries</h3>
            <div className="mt-6 space-y-5">
              {history.length === 0 ? (
                <p className="text-sm leading-6 text-scholarly-muted">No interactions yet. Start with a voice query or typed prompt.</p>
              ) : null}
              {history.map((entry) => (
                <div className="group cursor-default" key={entry.id}>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-scholarly-muted">
                    {entry.role === "user" ? "User" : "Assistant"}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-ink group-hover:text-scholarly-primary">{entry.content}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl bg-[rgba(219,228,231,0.45)] p-4">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-scholarly-muted">Active Speaker</p>
            <p className="mt-2 text-sm font-bold text-scholarly-primary">
              {latestResponse?.recognized_user?.display_name ?? "Automatic speaker recognition"}
            </p>
          </div>
        </aside>

        <section className="space-y-8 lg:col-span-5 lg:order-2 order-1">
          <div className="text-center">
            <div className="relative inline-flex">
              <div className="voice-pulse flex h-24 w-24 items-center justify-center rounded-full bg-[linear-gradient(135deg,#34647d_0%,#275771_100%)] text-4xl text-white shadow-float">
                ●
              </div>
              <div className="absolute -right-10 -top-2 rounded-full bg-scholarly-tertiary px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-[#445269]">
                {statusText}
              </div>
            </div>
            <p className="mx-auto mt-6 max-w-xl text-lg italic leading-8 text-scholarly-muted">
              {message || latestResponse?.response_text || "Ask the quote bot by voice or text. The dashboard keeps transcript, match, and audio together."}
            </p>
          </div>

          <div className="editorial-card">
            <div className="flex flex-wrap items-center gap-3">
              <span className="status-pill">{statusText}</span>
              {latestResponse?.recognized_user ? (
                <span className="status-pill">
                  Identified {latestResponse.recognized_user.display_name}
                  {typeof latestResponse.recognized_user.confidence === "number"
                    ? ` · ${(latestResponse.recognized_user.confidence * 100).toFixed(1)}%`
                    : ""}
                </span>
              ) : null}
            </div>

            <label className="label mt-6">Profile selection</label>
            <select className="field" onChange={(event) => setSelectedUserId(event.target.value)} value={selectedUserId}>
              <option value="">Automatic speaker recognition</option>
              {initialUsers.map((user) => (
                <option key={user.user_id} value={user.user_id}>
                  {user.display_name}
                </option>
              ))}
            </select>

            <div className="mt-6">
              <AudioRecorder
                buttonLabel="Record Voice Query"
                onPermissionDenied={setPermissionWarning}
                onRecorded={sendVoiceQuery}
                onStatusChange={(status) => {
                  if (status === "recording") {
                    setStatusText("Listening...");
                  } else if (status === "blocked") {
                    setStatusText("Text fallback available");
                  } else if (!latestResponse) {
                    setStatusText("Ready");
                  }
                }}
              />
            </div>

            {permissionWarning ? <p className="notice-warning mt-5">{permissionWarning}</p> : null}

            <form className="mt-6 space-y-4" onSubmit={sendTextQuery}>
              <div className="rounded-2xl bg-scholarly-low p-4">
                <label className="label" htmlFor="text-query">
                  Text fallback
                </label>
                <textarea
                  className="field min-h-32 resize-y"
                  id="text-query"
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Complete this quote: To be or not to..."
                  value={message}
                />
              </div>
              <div className="flex flex-wrap gap-3">
                <button className="primary-button" type="submit">
                  Send Text Query
                </button>
                <button className="secondary-button" onClick={clearConversation} type="button">
                  End Session
                </button>
              </div>
            </form>

            {error ? <p className="notice-danger mt-5">{error}</p> : null}
          </div>
        </section>

        <aside className="min-h-[42rem] lg:col-span-4 lg:order-3 order-3">
          <QuoteResponseCard response={latestResponse} />
        </aside>
      </main>
    </div>
  );
}
