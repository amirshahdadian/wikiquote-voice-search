"use client";

interface VoiceWaveformProps {
  active: boolean;
  amplitude?: number;
}

const BAR_CONFIG = [
  { delay: 0.0, baseHeight: 8 },
  { delay: 0.1, baseHeight: 14 },
  { delay: 0.2, baseHeight: 20 },
  { delay: 0.05, baseHeight: 28 },
  { delay: 0.15, baseHeight: 20 },
  { delay: 0.25, baseHeight: 14 },
  { delay: 0.1, baseHeight: 8 },
];

export default function VoiceWaveform({
  active,
  amplitude = 1,
}: VoiceWaveformProps) {
  return (
    <div
      className="flex items-center justify-center gap-[3px]"
      aria-hidden="true"
    >
      {BAR_CONFIG.map((bar, i) => {
        const maxHeight = Math.max(6, bar.baseHeight * amplitude);
        const restHeight = Math.max(3, bar.baseHeight * 0.3);

        return (
          <span
            key={i}
            className={active ? "w-[3px] rounded-full animate-[bar-bounce_0.8s_ease-in-out_infinite]" : "w-[3px] rounded-full"}
            style={{
              background: active
                ? `linear-gradient(180deg, #c4b5fd 0%, #8b5cf6 100%)`
                : "rgba(255,255,255,0.2)",
              height: active ? maxHeight : restHeight,
              opacity: active ? undefined : 0.25,
              animationDelay: `${bar.delay}s`,
            }}
          />
        );
      })}
    </div>
  );
}
