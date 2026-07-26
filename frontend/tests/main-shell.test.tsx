import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import MainShell from "@/components/main-shell";

const apiMocks = vi.hoisted(() => ({
  autocompleteQuotes: vi.fn().mockResolvedValue([
    {
      quote_id: "quote-suggestion",
      quote_text: "Courage is grace under pressure.",
      author_name: "Ernest Hemingway",
      page_title: "Ernest Hemingway",
    },
  ]),
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
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    fetchHealth: vi.fn().mockResolvedValue(null),
    autocompleteQuotes: apiMocks.autocompleteQuotes,
    sendChatQuery: apiMocks.sendChatQuery,
  };
});

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("MainShell", () => {
  it("offers lexical quote completions without sending a chat request", async () => {
    const user = userEvent.setup();
    render(<MainShell initialUsers={[]} />);

    const input = screen.getByPlaceholderText("Type part of a quote…");
    await user.type(input, "Courage is");
    await user.click(
      await screen.findByRole("button", {
        name: /Courage is grace under pressure/i,
      }),
    );

    expect(apiMocks.autocompleteQuotes).toHaveBeenCalledWith(
      "Courage is",
      5,
      expect.any(AbortSignal),
    );
    expect(apiMocks.sendChatQuery).not.toHaveBeenCalled();
    expect(input).toHaveValue("Courage is grace under pressure.");
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
