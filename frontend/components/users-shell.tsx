"use client";

import { AnimatePresence, motion } from "motion/react";
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Mic,
  MicOff,
  Play,
  Pause,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  User,
  Volume2,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import type { UserProfile } from "@/lib/types";
import {
  createTtsPreview,
  deleteUserProfile,
  fetchUsers,
  reEnrollUser,
  registerUser,
  resolveApiUrl,
} from "@/lib/api";

const cn = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(" ");

// ── Voice label map ────────────────────────────────────────────────────────────
const VOICE_LABELS: Record<string, { label: string; flag: string }> = {
  af_heart:    { label: "Heart",    flag: "🇺🇸" },
  af_bella:    { label: "Bella",    flag: "🇺🇸" },
  af_nicole:   { label: "Nicole",   flag: "🇺🇸" },
  af_sarah:    { label: "Sarah",    flag: "🇺🇸" },
  af_sky:      { label: "Sky",      flag: "🇺🇸" },
  af_alloy:    { label: "Alloy",    flag: "🇺🇸" },
  af_aoede:    { label: "Aoede",    flag: "🇺🇸" },
  af_jessica:  { label: "Jessica",  flag: "🇺🇸" },
  af_kore:     { label: "Kore",     flag: "🇺🇸" },
  af_nova:     { label: "Nova",     flag: "🇺🇸" },
  af_river:    { label: "River",    flag: "🇺🇸" },
  am_adam:     { label: "Adam",     flag: "🇺🇸" },
  am_michael:  { label: "Michael",  flag: "🇺🇸" },
  am_echo:     { label: "Echo",     flag: "🇺🇸" },
  am_eric:     { label: "Eric",     flag: "🇺🇸" },
  am_fenrir:   { label: "Fenrir",   flag: "🇺🇸" },
  am_liam:     { label: "Liam",     flag: "🇺🇸" },
  am_onyx:     { label: "Onyx",     flag: "🇺🇸" },
  am_puck:     { label: "Puck",     flag: "🇺🇸" },
  bf_emma:     { label: "Emma",     flag: "🇬🇧" },
  bf_isabella: { label: "Isabella", flag: "🇬🇧" },
  bf_alice:    { label: "Alice",    flag: "🇬🇧" },
  bf_lily:     { label: "Lily",     flag: "🇬🇧" },
  bm_george:   { label: "George",   flag: "🇬🇧" },
  bm_lewis:    { label: "Lewis",    flag: "🇬🇧" },
  bm_daniel:   { label: "Daniel",   flag: "🇬🇧" },
  bm_fable:    { label: "Fable",    flag: "🇬🇧" },
};

function voiceLabel(style?: string | null) {
  if (!style) return null;
  const v = VOICE_LABELS[style];
  return v ? `${v.flag} ${v.label}` : style;
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface RecordedSample {
  id: string;
  blob: Blob;
  url: string;
  name: string;
}

// ── Avatar ────────────────────────────────────────────────────────────────────
function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" | "lg" }) {
  const letter = name.charAt(0).toUpperCase();
  const colors = [
    "from-violet-500 to-purple-700",
    "from-teal-500 to-cyan-700",
    "from-amber-500 to-orange-600",
    "from-rose-500 to-pink-700",
    "from-emerald-500 to-green-700",
    "from-sky-500 to-blue-700",
  ];
  const color = colors[letter.charCodeAt(0) % colors.length];
  const sz = size === "lg" ? "w-14 h-14 text-xl" : size === "sm" ? "w-8 h-8 text-sm" : "w-10 h-10 text-base";
  return (
    <div className={cn(`bg-gradient-to-br ${color} rounded-2xl flex items-center justify-center font-bold text-white shrink-0`, sz)}>
      {letter}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function UsersShell({ initialUsers }: { initialUsers: UserProfile[] }) {
  const [users, setUsers] = useState<UserProfile[]>(initialUsers);
  const [isLoading, setIsLoading] = useState(false);
  const [reEnrollTarget, setReEnrollTarget] = useState<UserProfile | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserProfile | null>(null);
  const [showAddUser, setShowAddUser] = useState(false);
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  async function refreshUsers() {
    setIsLoading(true);
    try {
      setUsers(await fetchUsers());
    } finally {
      setIsLoading(false);
    }
  }

  async function deleteUser(userId: string) {
    await deleteUserProfile(userId);
    setUsers((prev) => prev.filter((u) => u.user_id !== userId));
    setDeleteTarget(null);
  }

  async function previewVoice(user: UserProfile) {
    if (previewingVoice === user.user_id) {
      audioRef.current?.pause();
      setPreviewingVoice(null);
      return;
    }
    setPreviewingVoice(user.user_id);
    try {
      const { audio_url } = await createTtsPreview({
        text: `Hello, my name is ${user.display_name}. This is my assigned voice.`,
        user_id: user.user_id,
      });
      if (!audio_url) throw new Error();
      const url = resolveApiUrl(audio_url) ?? "";
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = url;
      } else {
        audioRef.current = new Audio(url);
      }
      audioRef.current.onended = () => setPreviewingVoice(null);
      audioRef.current.onerror = () => setPreviewingVoice(null);
      await audioRef.current.play();
    } catch {
      setPreviewingVoice(null);
    }
  }

  return (
    <div className="min-h-dvh flex flex-col">
      {/* ── Header ── */}
      <header className="flex-none flex items-center justify-between px-5 md:px-8 py-4 border-b border-white/[0.06] glass-elevated sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="btn-ghost"
          >
            <ArrowLeft size={15} />
            Back
          </Link>
          <div className="w-px h-4 bg-white/[0.1]" />
          <h1 className="text-sm font-semibold text-white/90">Manage Users</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refreshUsers}
            disabled={isLoading}
            className="btn-ghost"
            title="Refresh"
          >
            <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
          </button>
          <button
            onClick={() => setShowAddUser(true)}
            className="btn-primary py-1.5 px-3 text-xs"
          >
            <Plus size={13} />
            Add user
          </button>
        </div>
      </header>

      {/* ── Body ── */}
      <main className="flex-1 px-4 md:px-8 py-8 max-w-4xl mx-auto w-full">
        {/* Page title */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="mb-8"
        >
          <h2 className="text-2xl font-bold tracking-tight text-white/90 mb-1">
            Enrolled <span className="gradient-text">Speakers</span>
          </h2>
          <p className="text-sm text-white/40">
            Each user has a unique voice for TTS responses and a speaker embedding for voice identification.
          </p>
        </motion.div>

        {/* ── User grid ── */}
        <AnimatePresence mode="popLayout">
          {users.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="glass ring-1 ring-white/5 rounded-2xl px-8 py-16 text-center"
            >
              <User size={32} className="mx-auto text-white/20 mb-3" />
              <p className="text-white/50 text-sm mb-1">No users enrolled yet</p>
              <p className="text-white/30 text-xs">Click "Add user" to enroll the first speaker</p>
            </motion.div>
          ) : (
            <motion.div
              key="grid"
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
            >
              {users.map((user, i) => (
                <motion.div
                  key={user.user_id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.35, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] }}
                  className="glass ring-1 ring-white/5 rounded-2xl p-5 flex flex-col gap-4 group hover:bg-white/[0.09] transition-colors duration-300"
                >
                  {/* Top row */}
                  <div className="flex items-start gap-3">
                    <Avatar name={user.display_name} size="md" />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-white/90 truncate leading-tight">
                        {user.display_name}
                      </p>
                      <p className="text-[11px] text-white/40 font-mono mt-0.5 truncate">
                        {user.user_id}
                      </p>
                    </div>
                  </div>

                  {/* Status badges */}
                  <div className="flex flex-wrap gap-1.5">
                    {/* Voice badge */}
                    {user.preferences?.style && (
                      <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 bg-violet-500/15 border border-violet-500/20 text-[11px] font-medium text-violet-300">
                        <Volume2 size={10} />
                        {voiceLabel(user.preferences.style)}
                      </span>
                    )}

                    {/* Embedding badge */}
                    {user.has_embedding ? (
                      <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 bg-emerald-500/15 border border-emerald-500/20 text-[11px] font-medium text-emerald-300">
                        <CheckCircle2 size={10} />
                        Voice ID active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 bg-white/[0.06] border border-white/[0.08] text-[11px] font-medium text-white/40">
                        <MicOff size={10} />
                        No voice ID
                      </span>
                    )}
                  </div>

                  {/* TTS speed pill */}
                  {user.preferences && (
                    <div className="flex gap-3 text-[11px] text-white/30">
                      <span>Speed <span className="text-white/60">{user.preferences.speaking_rate.toFixed(1)}×</span></span>
                      <span>Energy <span className="text-white/60">{user.preferences.energy_scale.toFixed(1)}×</span></span>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2 mt-auto pt-1 border-t border-white/[0.06]">
                    {/* Preview voice */}
                    <button
                      onClick={() => previewVoice(user)}
                      className={cn(
                        "flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2 text-xs font-medium transition-all duration-200",
                        previewingVoice === user.user_id
                          ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                          : "bg-white/[0.06] hover:bg-white/[0.11] text-white/60 hover:text-white border border-white/[0.08]"
                      )}
                      title="Preview voice"
                    >
                      {previewingVoice === user.user_id ? (
                        <><Pause size={12} /> Stop</>
                      ) : (
                        <><Play size={12} /> Preview</>
                      )}
                    </button>

                    {/* Re-enroll */}
                    <button
                      onClick={() => setReEnrollTarget(user)}
                      className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium bg-white/[0.06] hover:bg-white/[0.11] text-white/60 hover:text-white border border-white/[0.08] transition-all duration-200"
                      title="Re-record voice samples"
                    >
                      <RefreshCw size={12} />
                      Re-enroll
                    </button>

                    {/* Delete */}
                    <button
                      onClick={() => setDeleteTarget(user)}
                      className="flex items-center justify-center rounded-xl p-2 text-xs font-medium bg-white/[0.06] hover:bg-red-500/20 text-white/40 hover:text-red-300 border border-white/[0.08] hover:border-red-500/30 transition-all duration-200"
                      title="Delete user"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* ── Delete confirmation modal ── */}
      <AnimatePresence>
        {deleteTarget && (
          <ConfirmDeleteModal
            user={deleteTarget}
            onConfirm={() => deleteUser(deleteTarget.user_id)}
            onCancel={() => setDeleteTarget(null)}
          />
        )}
      </AnimatePresence>

      {/* ── Re-enroll modal ── */}
      <AnimatePresence>
        {reEnrollTarget && (
          <ReEnrollModal
            user={reEnrollTarget}
            onClose={() => setReEnrollTarget(null)}
            onSuccess={(updated) => {
              setUsers((prev) => prev.map((u) => u.user_id === updated.user_id ? updated : u));
              setReEnrollTarget(null);
            }}
          />
        )}
      </AnimatePresence>

      {/* ── Add user modal ── */}
      <AnimatePresence>
        {showAddUser && (
          <AddUserModal
            onClose={() => setShowAddUser(false)}
            onSuccess={(user) => {
              setUsers((prev) => [...prev, user]);
              setShowAddUser(false);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Confirm delete ─────────────────────────────────────────────────────────────
function ConfirmDeleteModal({
  user,
  onConfirm,
  onCancel,
}: {
  user: UserProfile;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <ModalOverlay onClose={onCancel}>
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: 12 }}
        transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
        className="glass ring-1 ring-white/5 rounded-2xl p-6 w-full max-w-sm shadow-glass-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-red-500/20 border border-red-500/30 flex items-center justify-center shrink-0">
            <Trash2 size={16} className="text-red-400" />
          </div>
          <div>
            <p className="font-semibold text-white/90 text-sm">Delete user</p>
            <p className="text-xs text-white/40 mt-0.5">This cannot be undone</p>
          </div>
        </div>
        <p className="text-sm text-white/60 mb-5">
          Remove <span className="text-white/90 font-medium">{user.display_name}</span> and
          their voice embedding from the system?
        </p>
        <div className="flex gap-2">
          <button onClick={onCancel} className="btn-secondary flex-1 text-xs py-2">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2 text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors duration-200"
          >
            <Trash2 size={12} />
            Delete
          </button>
        </div>
      </motion.div>
    </ModalOverlay>
  );
}

// ── Re-enroll modal ────────────────────────────────────────────────────────────
function ReEnrollModal({
  user,
  onClose,
  onSuccess,
}: {
  user: UserProfile;
  onClose: () => void;
  onSuccess: (updated: UserProfile) => void;
}) {
  return (
    <ModalOverlay onClose={onClose}>
      <RecordingForm
        title={`Re-enroll ${user.display_name}`}
        subtitle="Record 3 new voice samples to update the speaker embedding."
        onClose={onClose}
        onSubmit={async (samples) => {
          return reEnrollUser(
            user.user_id,
            samples.map((sample) => ({
              blob: sample.blob,
              name: `${sample.name}.${sample.blob.type.includes("webm") ? "webm" : "wav"}`,
            }))
          );
        }}
        onSuccess={onSuccess}
      />
    </ModalOverlay>
  );
}

// ── Add user modal ─────────────────────────────────────────────────────────────
function AddUserModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: (user: UserProfile) => void;
}) {
  const [displayName, setDisplayName] = useState("");

  return (
    <ModalOverlay onClose={onClose}>
      <RecordingForm
        title="Enroll new user"
        subtitle="Enter a name and record 3 voice samples."
        nameField={{ value: displayName, onChange: setDisplayName }}
        onClose={onClose}
        onSubmit={async (samples) => {
          if (!displayName.trim()) throw new Error("Name is required");
          return registerUser({
            display_name: displayName.trim(),
            pitch_scale: 1.0,
            speaking_rate: 1.0,
            energy_scale: 1.0,
            audio_samples: samples.map((sample) => ({
              blob: sample.blob,
              name: `${sample.name}.${sample.blob.type.includes("webm") ? "webm" : "wav"}`,
            })),
          });
        }}
        onSuccess={onSuccess}
      />
    </ModalOverlay>
  );
}

// ── Shared recording form ──────────────────────────────────────────────────────
function RecordingForm({
  title,
  subtitle,
  nameField,
  onClose,
  onSubmit,
  onSuccess,
}: {
  title: string;
  subtitle: string;
  nameField?: { value: string; onChange: (v: string) => void };
  onClose: () => void;
  onSubmit: (samples: RecordedSample[]) => Promise<UserProfile>;
  onSuccess: (user: UserProfile) => void;
}) {
  const [samples, setSamples] = useState<RecordedSample[]>([]);
  const [recordingState, setRecordingState] = useState<"idle" | "recording">("idle");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(blob);
        setSamples((prev) => [
          ...prev,
          { id: `rec-${Date.now()}`, blob, url, name: `Sample ${prev.length + 1}` },
        ]);
        setRecordingState("idle");
      };
      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setRecordingState("recording");
    } catch {
      setError("Microphone access denied.");
    }
  }

  function stopRecording() {
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
    setSamples((prev) => [
      ...prev,
      ...files.map((f) => ({
        id: `file-${Date.now()}-${Math.random()}`,
        blob: f,
        url: URL.createObjectURL(f),
        name: f.name,
      })),
    ]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const user = await onSubmit(samples);
      onSuccess(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = samples.length >= 3 && !submitting &&
    (nameField ? nameField.value.trim().length > 0 : true);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 16 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96, y: 16 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="glass ring-1 ring-white/5 rounded-2xl p-6 w-full max-w-md shadow-glass-lg"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h2 className="font-semibold text-white/90 text-base">{title}</h2>
          <p className="text-xs text-white/40 mt-0.5">{subtitle}</p>
        </div>
        <button onClick={onClose} className="btn-ghost p-1.5 -mr-1 -mt-1">
          <X size={15} />
        </button>
      </div>

      {/* Name field */}
      {nameField && (
        <div className="mb-4">
          <label className="text-xs font-medium text-white/50 mb-1.5 block">Name</label>
          <input
            type="text"
            value={nameField.value}
            onChange={(e) => nameField.onChange(e.target.value)}
            placeholder="e.g. Alice"
            className="input-glass text-sm py-2.5"
            autoFocus
          />
        </div>
      )}

      {/* Samples list */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-white/50">
            Voice samples
          </label>
          <span className={cn(
            "text-[11px] font-semibold transition-colors",
            samples.length >= 3 ? "text-emerald-400" : "text-white/30"
          )}>
            {samples.length}/3 {samples.length >= 3 ? "✓" : "required"}
          </span>
        </div>

        <div className="space-y-1.5 mb-2">
          <AnimatePresence>
            {samples.map((s) => (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-center gap-2 rounded-xl bg-white/[0.05] border border-white/[0.07] px-3 py-2"
              >
                <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                <span className="text-xs text-white/60 flex-1 truncate">{s.name}</span>
                <audio src={s.url} controls className="h-6 w-28 opacity-60" />
                <button
                  onClick={() => removeSample(s.id)}
                  className="text-white/30 hover:text-red-400 transition-colors ml-1"
                >
                  <X size={12} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Record / upload buttons */}
        <div className="flex gap-2">
          <button
            onClick={recordingState === "idle" ? startRecording : stopRecording}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-semibold border transition-all duration-300",
              recordingState === "recording"
                ? "bg-red-600/80 border-red-500/50 text-white shadow-[0_0_20px_rgba(239,68,68,0.3)]"
                : "bg-white/[0.07] border-white/[0.1] text-white/70 hover:bg-white/[0.11]"
            )}
          >
            {recordingState === "recording" ? (
              <><span className="w-2 h-2 rounded-sm bg-white animate-pulse" /> Stop</>
            ) : (
              <><Mic size={13} /> Record</>
            )}
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 rounded-xl px-3 py-2.5 text-xs font-medium bg-white/[0.06] border border-white/[0.08] text-white/50 hover:text-white hover:bg-white/[0.10] transition-all duration-200"
          >
            <Upload size={12} /> Upload
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*"
            multiple
            className="hidden"
            onChange={handleFileUpload}
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2 mb-3">
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="btn-primary w-full justify-center py-2.5"
      >
        {submitting ? (
          <><Loader2 size={14} className="animate-spin" /> Processing…</>
        ) : (
          "Save"
        )}
      </button>
    </motion.div>
  );
}

// ── Modal overlay ─────────────────────────────────────────────────────────────
function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(7,8,15,0.8)", backdropFilter: "blur(8px)" }}
      onClick={onClose}
    >
      {children}
    </motion.div>
  );
}
