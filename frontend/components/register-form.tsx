"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import SampleCollection from "@/components/sample-collection";
import { registerUser } from "@/lib/api";
import { LocalAudioSample, UserProfile } from "@/lib/types";

export default function RegisterForm() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [groupIdentifier, setGroupIdentifier] = useState("");
  const [pitchScale, setPitchScale] = useState(1);
  const [speakingRate, setSpeakingRate] = useState(1);
  const [energyScale, setEnergyScale] = useState(1);
  const [samples, setSamples] = useState<LocalAudioSample[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (!displayName.trim()) {
      setError("Display name is required.");
      return;
    }

    if (samples.length < 3) {
      setError("At least 3 audio samples are required before registration.");
      return;
    }

    setIsSubmitting(true);

    try {
      const payload: UserProfile = await registerUser({
        display_name: displayName.trim(),
        group_identifier: groupIdentifier.trim() || undefined,
        pitch_scale: pitchScale,
        speaking_rate: speakingRate,
        energy_scale: energyScale,
        audio_samples: samples.map((sample) => ({ blob: sample.blob, name: sample.name })),
      });
      setNotice(`Profile saved for ${payload.display_name}. Redirecting to the main app...`);
      router.push(`/app?user=${encodeURIComponent(payload.user_id)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Registration failed.");
    } finally {
      setIsSubmitting(false);
    }
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
              <Link className="nav-link" href="/">
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
          <Link className="secondary-button" href="/">
            Return to Discovery
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-6 pb-16 pt-10 lg:px-10">
        <div className="mx-auto mb-12 max-w-2xl">
          <div className="mb-4 flex items-end justify-between">
            <span className="font-headline text-3xl font-extrabold text-scholarly-primary">Step 02</span>
            <span className="text-xs font-semibold uppercase tracking-[0.26em] text-scholarly-muted">Voice Synthesis Profile</span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-scholarly-high">
            <div className="h-full w-2/3 bg-scholarly-primary" />
          </div>
        </div>

        <form className="grid items-start gap-10 lg:grid-cols-[0.78fr_1.22fr]" onSubmit={handleSubmit}>
          <aside className="space-y-8 lg:sticky lg:top-28">
            <div>
              <h1 className="text-4xl font-extrabold leading-tight text-ink">
                Create Your <span className="italic text-scholarly-primary">Acoustic Identity</span>
              </h1>
              <p className="mt-4 text-base leading-7 text-scholarly-muted">
                Register a new user with voice samples for speaker recognition and a saved TTS response profile.
              </p>
            </div>

            <div className="rounded-2xl border-l-4 border-scholarly-primary bg-scholarly-low p-6">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-scholarly-primary">Researcher Tip</p>
              <p className="mt-3 text-sm leading-6 text-scholarly-muted">
                Read clearly in a quiet environment. Vary the content slightly across samples to improve recognition quality.
              </p>
            </div>

            <div className="rounded-2xl bg-white p-6 shadow-card">
              <p className="text-sm font-semibold text-ink">Enrollment prompts</p>
              <ol className="mt-4 space-y-2 text-sm leading-6 text-scholarly-muted">
                <li>1. Read a quote naturally for 10 to 20 seconds.</li>
                <li>2. Vary the content slightly between samples.</li>
                <li>3. Keep background noise low.</li>
              </ol>
            </div>
          </aside>

          <section className="space-y-6">
            <div className="editorial-card">
              <div className="space-y-2 text-center">
                <h2 className="text-2xl font-bold text-ink">Record Voice Sample</h2>
                <p className="text-sm text-scholarly-muted">Please read the following sentence aloud:</p>
                <blockquote className="rounded-xl bg-scholarly-low px-6 py-5 text-lg italic text-scholarly-primary">
                  &quot;The precision of language is the beginning of all scholarship and digital curation.&quot;
                </blockquote>
              </div>

              <div className="mt-8">
                <SampleCollection onChange={setSamples} onPermissionDenied={(message) => setNotice(message)} samples={samples} />
              </div>
            </div>

            <div className="editorial-card">
              <h2 className="text-2xl font-bold text-ink">Researcher Details</h2>
              <div className="mt-6 grid gap-6 md:grid-cols-2">
                <div>
                  <label className="label" htmlFor="display-name">
                    Display name
                  </label>
                  <input
                    className="field"
                    id="display-name"
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder="Dr. Julian Vane"
                    value={displayName}
                  />
                </div>

                <div>
                  <label className="label" htmlFor="group-identifier">
                    Group identifier
                  </label>
                  <input
                    className="field"
                    id="group-identifier"
                    onChange={(event) => setGroupIdentifier(event.target.value)}
                    placeholder="NLP Research Lab"
                    value={groupIdentifier}
                  />
                </div>
              </div>

              <div className="mt-8">
                <h3 className="text-lg font-bold text-ink">TTS Preferences</h3>
                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  <div className="rounded-xl border-2 border-scholarly-primary bg-[rgba(196,231,255,0.18)] p-4">
                    <p className="font-headline text-sm font-bold">Naturalist</p>
                    <p className="mt-1 text-xs text-scholarly-muted">Soft, balanced</p>
                  </div>
                  <div className="rounded-xl bg-scholarly-low p-4">
                    <p className="font-headline text-sm font-bold">Authority</p>
                    <p className="mt-1 text-xs text-scholarly-muted">Deep, resonant</p>
                  </div>
                  <div className="rounded-xl bg-scholarly-low p-4">
                    <p className="font-headline text-sm font-bold">Clarity</p>
                    <p className="mt-1 text-xs text-scholarly-muted">Crisp, analytical</p>
                  </div>
                </div>
              </div>

              <div className="mt-8 grid gap-6 md:grid-cols-3">
                <div>
                  <label className="label" htmlFor="pitch-scale">
                    Pitch scale: {pitchScale.toFixed(1)}
                  </label>
                  <input
                    className="w-full accent-scholarly-primary"
                    id="pitch-scale"
                    max={2}
                    min={0.5}
                    onChange={(event) => setPitchScale(Number(event.target.value))}
                    step={0.1}
                    type="range"
                    value={pitchScale}
                  />
                </div>

                <div>
                  <label className="label" htmlFor="speaking-rate">
                    Speaking rate: {speakingRate.toFixed(1)}
                  </label>
                  <input
                    className="w-full accent-scholarly-primary"
                    id="speaking-rate"
                    max={1.5}
                    min={0.5}
                    onChange={(event) => setSpeakingRate(Number(event.target.value))}
                    step={0.1}
                    type="range"
                    value={speakingRate}
                  />
                </div>

                <div>
                  <label className="label" htmlFor="energy-scale">
                    Energy scale: {energyScale.toFixed(1)}
                  </label>
                  <input
                    className="w-full accent-scholarly-primary"
                    id="energy-scale"
                    max={1.5}
                    min={0.5}
                    onChange={(event) => setEnergyScale(Number(event.target.value))}
                    step={0.1}
                    type="range"
                    value={energyScale}
                  />
                </div>
              </div>

              {notice ? <p className="notice-success mt-6">{notice}</p> : null}
              {error ? <p className="notice-danger mt-6">{error}</p> : null}

              <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-scholarly-line/20 pt-6">
                <button className="text-sm font-bold text-scholarly-primary hover:underline" type="button">
                  Save Draft
                </button>
                <div className="flex flex-wrap gap-3">
                  <Link className="secondary-button" href="/app">
                    Skip to Main App
                  </Link>
                  <button className="primary-button" disabled={isSubmitting} type="submit">
                    {isSubmitting ? "Saving Profile..." : "Save Profile"}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </form>
      </main>
    </div>
  );
}
