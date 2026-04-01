import React from "react";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import LandingShell from "@/components/landing-shell";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("LandingShell", () => {
  it("renders calls to action and registered profiles", () => {
    render(
      <LandingShell
        featuredQuote={null}
        users={[
          {
            user_id: "amir",
            display_name: "Amir",
            group_identifier: "nlp-a",
            has_embedding: true,
            preferences: {
              pitch_scale: 1,
              speaking_rate: 1,
              energy_scale: 1,
              style: "neutral",
            },
          },
        ]}
      />,
    );

    expect(screen.getByText(/Start Speaking/i)).toBeInTheDocument();
    expect(screen.getByText(/Register New User/i)).toBeInTheDocument();
    expect(screen.getByText(/Continue as existing profile/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Amir")).toBeInTheDocument();
  });
});
