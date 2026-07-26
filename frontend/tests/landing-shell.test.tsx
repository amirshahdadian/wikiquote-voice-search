import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import LandingShell from "@/components/landing-shell";
import MainShell from "@/components/main-shell";

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    fetchHealth: vi.fn().mockResolvedValue(null),
    sendChatQuery: vi.fn().mockResolvedValue({
      conversation_id: "conversation-1",
      intent_type: "topic",
      response_text: '"Courage is grace under pressure." — Ernest Hemingway',
      best_quote: {
        quote_id: "quote-1",
        quote_text: "Courage is grace under pressure.",
        author_name: "Ernest Hemingway",
        source_title: null,
        page_title: "Courage",
        citation: "Interview, 1954",
        search_type: "hybrid",
      },
      related_quotes: [],
      audio_url: null,
      warnings: [],
    }),
  };
});

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

  it("renders provenance from the canonical chat response", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    const user = userEvent.setup();
    render(<MainShell initialUsers={[]} />);

    await user.type(
      screen.getByPlaceholderText("Type part of a quote…"),
      "courage",
    );
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(
      (await screen.findAllByText(/Courage is grace under pressure/)).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Wikiquote: Courage/i)).toBeInTheDocument();
    expect(screen.getByText(/Interview, 1954/i)).toBeInTheDocument();
  });
});
