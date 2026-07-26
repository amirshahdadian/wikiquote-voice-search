"use client";

import { useEffect, useRef, useState } from "react";

export type RecordedAudio = {
  blob: Blob;
  mimeType: string;
};

type RecorderStatus = "idle" | "recording" | "blocked";

type RecorderOptions = {
  onRecorded: (audio: RecordedAudio) => void;
  onError?: (message: string) => void;
  onStatusChange?: (status: RecorderStatus) => void;
};

export function audioExtension(mimeType: string): string {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("mp4") || mimeType.includes("aac")) return "m4a";
  if (mimeType.includes("mpeg")) return "mp3";
  if (mimeType.includes("wav")) return "wav";
  return "webm";
}

export function useAudioRecorder({
  onRecorded,
  onError,
  onStatusChange,
}: RecorderOptions) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  function updateStatus(next: RecorderStatus) {
    setStatus(next);
    onStatusChange?.(next);
  }

  useEffect(() => {
    return () => {
      if (recorderRef.current) {
        recorderRef.current.onstop = null;
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function start() {
    if (!("MediaRecorder" in window) || !navigator.mediaDevices?.getUserMedia) {
      const message = "This browser does not support in-browser audio recording.";
      updateStatus("blocked");
      onError?.(message);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const mimeType = recorder.mimeType || "audio/webm";
        onRecorded({
          blob: new Blob(chunksRef.current, { type: mimeType }),
          mimeType,
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        updateStatus("idle");
      };
      recorder.start();
      updateStatus("recording");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Microphone permission was denied.";
      updateStatus("blocked");
      onError?.(message);
    }
  }

  function stop() {
    recorderRef.current?.stop();
  }

  return { status, start, stop };
}
