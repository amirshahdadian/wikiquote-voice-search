"use client";

import Link from "next/link";
import { useState } from "react";

import { QuoteResult, UserProfile } from "@/lib/types";

type LandingShellProps = {
  users: UserProfile[];
  featuredQuote: QuoteResult | null;
};

export default function LandingShell({ users, featuredQuote }: LandingShellProps) {
  const [selectedUserId, setSelectedUserId] = useState(users[0]?.user_id ?? "");

  return (
    <div className="page-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="flex items-center gap-8">
            <Link className="brand" href="/">
              Which Quote?
            </Link>
            <nav className="hidden items-center gap-6 md:flex">
              <Link className="nav-link-active" href="/">
                Discover
              </Link>
              <Link className="nav-link" href="/app">
                Dashboard
              </Link>
              <Link className="nav-link" href="/profile">
                Profile
              </Link>
            </nav>
          </div>
          <div className="hidden items-center gap-3 md:flex">
            <span className="status-pill">NLP University Project</span>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-16 px-6 pb-16 pt-10 lg:px-10 lg:pt-14">
        <section className="editorial-hero grid items-center gap-10 rounded-[2rem] px-8 py-12 shadow-card lg:grid-cols-[1.2fr_0.8fr] lg:px-12 lg:py-16">
          <div>
            <span className="kicker">Voice-First Quote Research</span>
            <h1 className="headline-display mt-6">
              Voice-First <span className="italic text-scholarly-primary">Curated Wisdom.</span>
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-scholarly-muted">
              Ask for a quote out loud, let the system identify the speaker, search Wikiquote through the graph, and answer
              back with a saved voice profile.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link className="primary-button" href="/app">
                Start Speaking
              </Link>
              <Link className="secondary-button" href="/register">
                Register New User
              </Link>
            </div>
          </div>

          <div className="relative">
            <div className="rounded-[1.75rem] bg-[linear-gradient(135deg,rgba(52,100,125,0.95),rgba(39,87,113,0.85))] p-8 text-white shadow-float">
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-white/70">Graph Database</p>
              <p className="mt-6 text-4xl font-extrabold font-headline">450k+</p>
              <p className="mt-2 max-w-sm text-sm leading-6 text-white/80">
                Connected quote, speaker, topic, and source nodes powering semantic retrieval beyond plain text search.
              </p>
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-white/10 p-4 backdrop-blur">
                  <p className="text-xs uppercase tracking-[0.18em] text-white/70">Recognition</p>
                  <p className="mt-2 text-lg font-semibold">Multi-user speaker ID</p>
                </div>
                <div className="rounded-xl bg-white/10 p-4 backdrop-blur">
                  <p className="text-xs uppercase tracking-[0.18em] text-white/70">Playback</p>
                  <p className="mt-2 text-lg font-semibold">Personalized TTS response</p>
                </div>
              </div>
            </div>
            <div className="absolute -bottom-6 -left-4 max-w-xs rounded-2xl bg-white/90 p-5 shadow-float backdrop-blur">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-scholarly-primary">Precision Layer</p>
              <p className="mt-3 text-sm leading-6 text-scholarly-muted">
                Autocomplete, attribution, and topic-aware retrieval stay visible even when microphone access is blocked.
              </p>
            </div>
          </div>
        </section>

        <section className="grid gap-6 md:grid-cols-3">
          <div className="metric-card">
            <p className="text-lg font-bold font-headline text-ink">Quote retrieval</p>
            <p className="mt-3 text-sm leading-6 text-scholarly-muted">
              Autocomplete, partial-quote lookup, attribution, and topic search backed by Neo4j.
            </p>
          </div>
          <div className="metric-card">
            <p className="text-lg font-bold font-headline text-ink">Voice recognition</p>
            <p className="mt-3 text-sm leading-6 text-scholarly-muted">
              Recognize returning speakers from stored NeMo TitaNet embeddings and keep context user-aware.
            </p>
          </div>
          <div className="metric-card">
            <p className="text-lg font-bold font-headline text-ink">Personalized responses</p>
            <p className="mt-3 text-sm leading-6 text-scholarly-muted">
              Generate spoken answers with each user&apos;s saved pitch, speed, and energy settings.
            </p>
          </div>
        </section>

        <section className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="editorial-card">
            <p className="kicker">Continue as existing profile</p>
            <p className="mt-5 text-sm leading-6 text-scholarly-muted">
              Jump directly into the app with a saved profile, or leave recognition automatic and let the system identify the
              speaker from the recording.
            </p>
            <label className="label mt-8">Saved profiles</label>
            <select className="field" onChange={(event) => setSelectedUserId(event.target.value)} value={selectedUserId}>
              {users.length === 0 ? <option value="">No registered profiles yet</option> : null}
              {users.map((user) => (
                <option key={user.user_id} value={user.user_id}>
                  {user.display_name}
                </option>
              ))}
            </select>

            <Link
              aria-disabled={!selectedUserId}
              className={`mt-5 w-full ${selectedUserId ? "primary-button" : "secondary-button pointer-events-none opacity-50"}`}
              href={selectedUserId ? `/app?user=${encodeURIComponent(selectedUserId)}` : "/app"}
            >
              Continue to Interaction
            </Link>

            <div className="mt-8 space-y-4 rounded-2xl bg-scholarly-low p-5">
              <p className="text-sm font-semibold text-ink">Before you start</p>
              <p className="text-sm leading-6 text-scholarly-muted">
                The browser will ask for microphone permission the first time you record.
              </p>
              <p className="text-sm leading-6 text-scholarly-muted">
                If access is denied, the app still supports typed prompts and uploaded audio clips.
              </p>
            </div>
          </div>

          <div className="grid gap-6">
            <div className="editorial-card bg-scholarly-low">
              <p className="kicker">Methodology</p>
              <h2 className="mt-5 text-3xl font-extrabold tracking-tight text-ink">Bridging spoken input and archived knowledge.</h2>
              <div className="mt-8 grid gap-6 md:grid-cols-3">
                <div className="rounded-xl bg-white p-5">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-scholarly-primary">1</p>
                  <p className="mt-3 font-headline text-lg font-bold">Voice Input Analysis</p>
                </div>
                <div className="rounded-xl bg-white p-5">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-scholarly-primary">2</p>
                  <p className="mt-3 font-headline text-lg font-bold">Semantic Graph Search</p>
                </div>
                <div className="rounded-xl bg-white p-5">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-scholarly-primary">3</p>
                  <p className="mt-3 font-headline text-lg font-bold">Contextual TTS Synthesis</p>
                </div>
              </div>
            </div>

            {featuredQuote ? (
              <div className="editorial-card">
                <p className="kicker">Random Quote</p>
                <blockquote className="mt-5 text-2xl leading-10 text-ink">“{featuredQuote.quote_text}”</blockquote>
                <p className="mt-4 text-sm text-scholarly-muted">
                  {featuredQuote.author_name} · {featuredQuote.source_title}
                </p>
              </div>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
