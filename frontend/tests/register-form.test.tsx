import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import RegisterForm from "@/components/register-form";

const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

describe("RegisterForm", () => {
  it("enforces the minimum number of enrollment samples before submit", async () => {
    render(<RegisterForm />);

    fireEvent.change(screen.getByLabelText(/Display name/i), {
      target: { value: "Amir" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save Profile/i }));

    expect(await screen.findByText(/At least 3 audio samples are required/i)).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
