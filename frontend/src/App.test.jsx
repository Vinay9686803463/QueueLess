import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  };
}

function mockFetch(handlers) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    for (const [pattern, response] of handlers) {
      if (String(url).includes(pattern)) {
        return jsonResponse(response.data, response.status ?? 200);
      }
    }
    return jsonResponse({ message: "not found" }, 404);
  });
}

describe("QueueLess frontend", () => {
  let user;

  beforeEach(() => {
    user = userEvent.setup();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("shows the backend as online after the health check", async () => {
    mockFetch([["/api/health", { data: {} }]]);
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/System online/i)).toBeInTheDocument();
    });
  });

  it("renders the customer check-in experience", async () => {
    mockFetch([["/api/health", { data: {} }]]);
    render(<App />);
    expect(await screen.findByText(/A BETTER WAY TO WAIT/i)).toBeInTheDocument();
    expect(screen.getByText(/Skip the waiting room/i)).toBeInTheDocument();
  });

  it("renders the admin login experience", async () => {
    mockFetch([["/api/health", { data: {} }]]);
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Admin portal/i }));
    expect(await screen.findByText(/Welcome back/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sign in to dashboard/i })).toBeInTheDocument();
  });
});
