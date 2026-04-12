"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import SampleCollection from "@/components/sample-collection";
import {
  createTtsPreview,
  deleteUserProfile,
  fetchUser,
  reEnrollUser,
  resolveApiUrl,
  updateUserPreferences,
} from "@/lib/api";
import { LocalAudioSample, UserPreferences, UserProfile } from "@/lib/types";

type ProfileShellProps = {
  initialUsers: UserProfile[];
};

const defaultPreferences: UserPreferences = {
  pitch_scale: 1,
  speaking_rate: 1,
  energy_scale: 1,
  style: "neutral",
};

export default function ProfileShell({ initialUsers }: ProfileShellProps) {
  const [users, setUsers] = useState(initialUsers);
  const [selectedUserId, setSelectedUserId] = useState(initialUsers[0]?.user_id ?? "");
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(initialUsers[0] ?? null);
  const [preferences, setPreferences] = useState<UserPreferences>(initialUsers[0]?.preferences ?? defaultPreferences);
  const [previewText, setPreviewText] = useState("The best matching quote is knowledge is power.");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [reEnrollSamples, setReEnrollSamples] = useState<LocalAudioSample[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      if (!selectedUserId) {
        setCurrentUser(null);
        return;
      }

      const profile = await fetchUser(selectedUserId);
      if (profile) {
        setCurrentUser(profile);
        setPreferences(profile.preferences ?? defaultPreferences);
      }
    }

    loadProfile();
  }, [selectedUserId]);

  async function savePreferences() {
    if (!selectedUserId) {
      return;
    }

    setError(null);
    setMessage(null);
    setIsSaving(true);

    try {
      const updated = await updateUserPreferences(selectedUserId, preferences);
      setCurrentUser(updated);
      setUsers((current) => current.map((user) => (user.user_id === updated.user_id ? updated : user)));
      setMessage("Voice preferences updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save preferences.");
    } finally {
      setIsSaving(false);
    }
  }

  async function previewVoice() {
    setError(null);
    setMessage(null);

    try {
      const payload = await createTtsPreview({
        text: previewText,
        user_id: selectedUserId || undefined,
        preferences,
      });
      setPreviewUrl(resolveApiUrl(payload.audio_url) ?? null);
      setMessage(payload.warnings?.length ? payload.warnings.join(", ") : "Preview audio generated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not generate preview audio.");
    }
  }

  async function reEnroll() {
    if (!selectedUserId) {
      return;
    }
    if (reEnrollSamples.length < 3) {
      setError("At least 3 audio samples are required for re-enrollment.");
      return;
    }

    setError(null);
    setMessage(null);
    setIsSaving(true);

    try {
      const updated = await reEnrollUser(
        selectedUserId,
        reEnrollSamples.map((sample) => ({ blob: sample.blob, name: sample.name }))
      );
      setCurrentUser(updated);
      setUsers((current) => current.map((user) => (user.user_id === updated.user_id ? updated : user)));
      setReEnrollSamples([]);
      setMessage("Speaker embedding updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Re-enrollment failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteProfile() {
    if (!selectedUserId) {
      return;
    }

    const confirmed = window.confirm(`Delete the profile "${selectedUserId}"?`);
    if (!confirmed) {
      return;
    }

    setError(null);
    setMessage(null);
    setIsSaving(true);

    try {
      await deleteUserProfile(selectedUserId);
      const remainingUsers = users.filter((user) => user.user_id !== selectedUserId);
      setUsers(remainingUsers);
      setSelectedUserId(remainingUsers[0]?.user_id ?? "");
      setCurrentUser(remainingUsers[0] ?? null);
      setPreferences(remainingUsers[0]?.preferences ?? defaultPreferences);
      setPreviewUrl(null);
      setMessage("Profile deleted.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Delete failed.");
    } finally {
      setIsSaving(false);
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
              <Link className="nav-link" href="/app">
                Dashboard
              </Link>
              <Link className="nav-link" href="/">
                Discover
              </Link>
              <Link className="nav-link-active" href="/profile">
                Profile
              </Link>
            </nav>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link className="secondary-button" href="/app">
              Back to App
            </Link>
            <Link className="secondary-button" href="/register">
              Register Another User
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-6 pb-16 pt-10 lg:px-10">
        <div className="mb-10">
          <h1 className="text-4xl font-extrabold tracking-tight text-ink">Profile & Preferences</h1>
          <p className="mt-2 text-base text-scholarly-muted">
            Manage identity, voice synthesis, and recognition quality for saved researchers.
          </p>
        </div>

        {users.length === 0 ? (
          <div className="editorial-card">
            <p className="text-lg text-ink">No saved users yet.</p>
            <p className="mt-3 text-sm leading-6 text-scholarly-muted">
              Create a profile first to use speaker recognition and personalized response audio.
            </p>
            <Link className="primary-button mt-6" href="/register">
              Register a User
            </Link>
          </div>
        ) : (
          <section className="grid gap-8 lg:grid-cols-12">
            <div className="space-y-8 lg:col-span-7">
              <section className="editorial-card">
                <div className="mb-8 flex items-center gap-4">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-scholarly-primarySoft text-2xl text-scholarly-primary">
                    ●
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-ink">User Identity</h2>
                    <p className="text-sm text-scholarly-muted">Voice-authenticated profile</p>
                  </div>
                </div>

                <label className="label">Registered users</label>
                <select className="field" onChange={(event) => setSelectedUserId(event.target.value)} value={selectedUserId}>
                  {users.map((user) => (
                    <option key={user.user_id} value={user.user_id}>
                      {user.display_name}
                    </option>
                  ))}
                </select>

                {currentUser ? (
                  <div className="mt-6 space-y-4">
                    <div className="rounded-xl border-l-4 border-scholarly-primary bg-scholarly-low p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-scholarly-muted">Detected name</p>
                      <p className="mt-2 text-lg font-medium text-ink">{currentUser.display_name}</p>
                    </div>
                    <div className="rounded-xl bg-scholarly-low p-5">
                      <h3 className="font-semibold text-ink">Voice Recognition Sample</h3>
                      <p className="mt-2 text-sm leading-6 text-scholarly-muted">
                        User ID: {currentUser.user_id}
                        {currentUser.group_identifier ? ` · Group: ${currentUser.group_identifier}` : ""}
                      </p>
                      <p className="mt-1 text-sm leading-6 text-scholarly-muted">
                        {currentUser.has_embedding ? "Voice embedding available" : "No voice embedding saved"}
                      </p>
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="editorial-card">
                <div className="mb-8 flex items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-scholarly-tertiary text-scholarly-primary">
                    ◌
                  </div>
                  <h2 className="text-xl font-bold text-ink">Text-to-Speech</h2>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-scholarly-muted">Voice Profile</label>
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    {["natural", "professional", "expressive"].map((style) => {
                      const active = (preferences.style ?? "neutral") === style;
                      return (
                        <button
                          className={`rounded-lg p-4 text-center ${active ? "border-2 border-scholarly-primary bg-[rgba(196,231,255,0.18)]" : "bg-scholarly-low"}`}
                          key={style}
                          onClick={() => setPreferences((current) => ({ ...current, style }))}
                          type="button"
                        >
                          <span className="text-xs font-medium capitalize text-ink">{style}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-8 grid gap-8 md:grid-cols-3">
                  <div>
                    <label className="label">Speaking rate: {preferences.speaking_rate.toFixed(1)}</label>
                    <input
                      className="w-full accent-scholarly-primary"
                      max={1.5}
                      min={0.5}
                      onChange={(event) => setPreferences((current) => ({ ...current, speaking_rate: Number(event.target.value) }))}
                      step={0.1}
                      type="range"
                      value={preferences.speaking_rate}
                    />
                  </div>
                  <div>
                    <label className="label">Pitch scale: {preferences.pitch_scale.toFixed(1)}</label>
                    <input
                      className="w-full accent-scholarly-primary"
                      max={2}
                      min={0.5}
                      onChange={(event) => setPreferences((current) => ({ ...current, pitch_scale: Number(event.target.value) }))}
                      step={0.1}
                      type="range"
                      value={preferences.pitch_scale}
                    />
                  </div>
                  <div>
                    <label className="label">Energy scale: {preferences.energy_scale.toFixed(1)}</label>
                    <input
                      className="w-full accent-scholarly-primary"
                      max={1.5}
                      min={0.5}
                      onChange={(event) => setPreferences((current) => ({ ...current, energy_scale: Number(event.target.value) }))}
                      step={0.1}
                      type="range"
                      value={preferences.energy_scale}
                    />
                  </div>
                </div>

                <div className="mt-6 flex flex-wrap gap-3">
                  <button className="primary-button" disabled={isSaving || !selectedUserId} onClick={savePreferences} type="button">
                    Save Preferences
                  </button>
                  <button className="secondary-button" disabled={!selectedUserId} onClick={deleteProfile} type="button">
                    Delete Profile
                  </button>
                </div>
              </section>
            </div>

            <div className="space-y-8 lg:col-span-5">
              <section className="editorial-card overflow-hidden p-0">
                <div className="flex items-center justify-between bg-[rgba(227,233,236,0.5)] px-6 py-5">
                  <h2 className="text-lg font-bold text-ink">Response Voice Preview</h2>
                </div>
                <div className="p-6">
                  <textarea
                    className="field min-h-28 resize-y"
                    onChange={(event) => setPreviewText(event.target.value)}
                    value={previewText}
                  />
                  <div className="mt-5 flex flex-wrap gap-3">
                    <button className="primary-button" disabled={!selectedUserId} onClick={previewVoice} type="button">
                      Generate Preview
                    </button>
                  </div>
                  {previewUrl ? <audio className="mt-5 w-full" controls src={previewUrl} /> : null}
                </div>
              </section>

              <section className="editorial-card">
                <h2 className="text-xl font-bold text-ink">Re-enroll speaker samples</h2>
                <p className="mt-3 text-sm leading-6 text-scholarly-muted">
                  Record fresh samples if recognition quality drops or if you want to replace the stored embedding.
                </p>
                <div className="mt-6">
                  <SampleCollection
                    disabled={!selectedUserId}
                    onChange={setReEnrollSamples}
                    onPermissionDenied={setMessage}
                    samples={reEnrollSamples}
                  />
                </div>
                <div className="mt-6 flex flex-wrap gap-3">
                  <button className="primary-button" disabled={isSaving || !selectedUserId} onClick={reEnroll} type="button">
                    Update Embedding
                  </button>
                </div>
              </section>

              {message ? <p className="notice-success">{message}</p> : null}
              {error ? <p className="notice-danger">{error}</p> : null}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
