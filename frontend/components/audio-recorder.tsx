"use client";

import { useEffect, useRef, useState } from "react";

import { LocalAudioSample } from "@/lib/types";

type RecorderStatus = "idle" | "recording" | "blocked";

type AudioRecorderProps = {
  buttonLabel?: string;
  disabled?: boolean;
  onRecorded: (sample: LocalAudioSample) => void;
  onPermissionDenied?: (message: string) => void;
  onStatusChange?: (status: RecorderStatus) => void;
};

function nextSampleId() {
  return globalThis.crypto?.randomUUID?.() ?? `sample-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function guessExtension(mimeType: string): string {
  if (mimeType.includes("ogg")) return ".ogg";
  if (mimeType.includes("mp4") || mimeType.includes("aac")) return ".m4a";
  if (mimeType.includes("mpeg")) return ".mp3";
  if (mimeType.includes("wav")) return ".wav";
  return ".webm";
}

export default function AudioRecorder({
  buttonLabel = "Record Audio",
  disabled = false,
  onRecorded,
  onPermissionDenied,
  onStatusChange,
}: AudioRecorderProps) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  function updateStatus(nextStatus: RecorderStatus) {
    setStatus(nextStatus);
    onStatusChange?.(nextStatus);
  }

  useEffect(() => {
    return () => {
      mediaRecorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function startRecording() {
    setError(null);

    if (!("MediaRecorder" in window) || !navigator.mediaDevices?.getUserMedia) {
      const message = "This browser does not support in-browser audio recording. Upload an audio file instead.";
      setError(message);
      updateStatus("blocked");
      onPermissionDenied?.(message);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      chunksRef.current = [];
      streamRef.current = stream;
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const sample: LocalAudioSample = {
          id: nextSampleId(),
          name: `recording-${Date.now()}${guessExtension(mimeType)}`,
          blob,
          url: URL.createObjectURL(blob),
          source: "recorded",
        };
        onRecorded(sample);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        mediaRecorderRef.current = null;
        updateStatus("idle");
      };

      recorder.start();
      updateStatus("recording");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Microphone permission was denied.";
      setError(message);
      updateStatus("blocked");
      onPermissionDenied?.(message);
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
  }

  return (
    <div className="rounded-2xl bg-scholarly-low p-5">
      <div className="flex flex-wrap items-center gap-3">
        <button
          className={status === "recording" ? "secondary-button" : "primary-button"}
          disabled={disabled || status === "recording"}
          onClick={startRecording}
          type="button"
        >
          {buttonLabel}
        </button>
        <button
          className="secondary-button"
          disabled={disabled || status !== "recording"}
          onClick={stopRecording}
          type="button"
        >
          Stop Recording
        </button>
        <span className="status-pill">{status === "recording" ? "Listening" : "Idle"}</span>
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
        Use the microphone for 10 to 20 seconds per sample. The backend will normalize the audio before ASR or speaker
        recognition.
      </p>

      {error ? <p className="notice-danger mt-4">{error}</p> : null}
    </div>
  );
}
