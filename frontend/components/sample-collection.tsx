"use client";

import type { ChangeEvent } from "react";

import AudioRecorder from "@/components/audio-recorder";
import { LocalAudioSample } from "@/lib/types";

type SampleCollectionProps = {
  samples: LocalAudioSample[];
  minimum?: number;
  disabled?: boolean;
  onChange: (samples: LocalAudioSample[]) => void;
  onPermissionDenied?: (message: string) => void;
};

function nextSampleId() {
  return globalThis.crypto?.randomUUID?.() ?? `sample-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function SampleCollection({
  samples,
  minimum = 3,
  disabled = false,
  onChange,
  onPermissionDenied,
}: SampleCollectionProps) {
  function addRecordedSample(sample: LocalAudioSample) {
    onChange([...samples, sample]);
  }

  function removeSample(sampleId: string) {
    const sample = samples.find((entry) => entry.id === sampleId);
    if (sample) {
      URL.revokeObjectURL(sample.url);
    }
    onChange(samples.filter((entry) => entry.id !== sampleId));
  }

  function handleFileUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) {
      return;
    }

    const uploadedSamples = files.map(
      (file): LocalAudioSample => ({
        id: nextSampleId(),
        name: file.name,
        blob: file,
        url: URL.createObjectURL(file),
        source: "uploaded",
      }),
    );

    onChange([...samples, ...uploadedSamples]);
    event.target.value = "";
  }

  return (
    <div className="space-y-4">
      <div className="notice-success">
        {samples.length}/{minimum} samples collected. Record or upload at least {minimum} voice samples.
      </div>

      <AudioRecorder
        buttonLabel="Record Sample"
        disabled={disabled}
        onPermissionDenied={onPermissionDenied}
        onRecorded={addRecordedSample}
      />

      <div className="rounded-2xl bg-scholarly-low p-5">
        <label className="label">Upload audio files</label>
        <input
          accept="audio/*"
          className="field file:mr-4 file:rounded-md file:border-0 file:bg-scholarly-primary file:px-4 file:py-2 file:font-medium file:text-white"
          disabled={disabled}
          multiple
          onChange={handleFileUpload}
          type="file"
        />
      </div>

      <div className="space-y-3">
        {samples.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-scholarly-line/40 px-4 py-6 text-sm text-scholarly-muted">
            No samples collected yet.
          </p>
        ) : null}

        {samples.map((sample, index) => (
          <div
            className="rounded-2xl bg-scholarly-low p-4"
            key={sample.id}
          >
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm font-medium text-ink">
                  Sample {index + 1} · {sample.source === "recorded" ? "Recorded" : "Uploaded"}
                </p>
                <p className="mt-1 text-xs text-scholarly-muted">{sample.name}</p>
              </div>
              <button
                className="secondary-button"
                disabled={disabled}
                onClick={() => removeSample(sample.id)}
                type="button"
              >
                Remove
              </button>
            </div>
            <audio className="mt-3 w-full" controls src={sample.url} />
          </div>
        ))}
      </div>
    </div>
  );
}
