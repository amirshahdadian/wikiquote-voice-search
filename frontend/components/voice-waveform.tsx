"use client";

import { motion } from "motion/react";

interface VoiceWaveformProps {
  active: boolean;
  amplitude?: number;
}

const BAR_COUNT = 7;

// Each bar has a natural "rest" height and animation duration offset
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
          <motion.span
            key={i}
            className="rounded-full w-[3px]"
            style={{
              background: active
                ? `linear-gradient(180deg, #c4b5fd 0%, #8b5cf6 100%)`
                : "rgba(255,255,255,0.2)",
            }}
            animate={
              active
                ? {
                    height: [restHeight, maxHeight, restHeight],
                    opacity: [0.5, 1, 0.5],
                  }
                : {
                    height: restHeight,
                    opacity: 0.25,
                  }
            }
            transition={
              active
                ? {
                    duration: 0.8,
                    delay: bar.delay,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }
                : { duration: 0.3, ease: "easeOut" }
            }
            initial={{ height: restHeight, opacity: 0.25 }}
          />
        );
      })}
    </div>
  );
}
