"use client";

import { useState } from "react";

import { LocalAudioSample } from "@/lib/types";
import { audioExtension, useAudioRecorder } from "@/lib/use-audio-recorder";

type RecorderStatus = "idle" | "recording" | "blocked";

type AudioRecorderProps = {
  buttonLabel?: string;
  disabled?: boolean;
  onRecorded: (sample: LocalAudioSample) => void;
  onPermissionDenied?: (message: string) => void;
  onStatusChange?: (status: RecorderStatus) => void;
};

export default function AudioRecorder({
  buttonLabel = "Record Audio",
  disabled = false,
  onRecorded,
  onPermissionDenied,
  onStatusChange,
}: AudioRecorderProps) {
  const [error, setError] = useState<string | null>(null);
  const recorder = useAudioRecorder({
    onRecorded: ({ blob, mimeType }) => {
      onRecorded({
        id: crypto.randomUUID(),
        name: `recording-${Date.now()}.${audioExtension(mimeType)}`,
        blob,
        url: URL.createObjectURL(blob),
        source: "recorded",
      });
    },
    onError: (message) => {
      setError(message);
      onPermissionDenied?.(message);
    },
    onStatusChange,
  });

  return (
    <div className="rounded-2xl bg-scholarly-low p-5">
      <div className="flex flex-wrap items-center gap-3">
        <button
          className={recorder.status === "recording" ? "secondary-button" : "primary-button"}
          disabled={disabled || recorder.status === "recording"}
          onClick={() => {
            setError(null);
            recorder.start();
          }}
          type="button"
        >
          {buttonLabel}
        </button>
        <button
          className="secondary-button"
          disabled={disabled || recorder.status !== "recording"}
          onClick={recorder.stop}
          type="button"
        >
          Stop Recording
        </button>
        <span className="status-pill">{recorder.status === "recording" ? "Listening" : "Idle"}</span>
      </div>

      <div className="mt-5 rounded-full bg-white px-6 py-4 shadow-sm">
        <div className="recording-bars">
          <span className="h-3" />
          <span className="h-7" />
          <span className="h-10" />
          <span className="h-5" />
          <span className="h-8" />
          <span className="h-4" />
        </div>
      </div>

      <p className="mt-4 text-sm leading-6 text-scholarly-muted">
        Use the microphone for 10 to 20 seconds per sample.
      </p>

      {error ? <p className="notice-danger mt-4">{error}</p> : null}
    </div>
  );
}
