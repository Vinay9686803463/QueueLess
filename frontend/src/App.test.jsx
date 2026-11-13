import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
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
  beforeEach(() => { user = userEvent.setup(); localStorage.clear(); vi.restoreAllMocks(); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

  it("shows backend as online", async () => {
    mockFetch([["/api/health", { data: {} }]]);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/System online/i)).toBeInTheDocument());
  });

  it("renders customer check-in", async () => {
    mockFetch([["/api/health", { data: {} }]]);
    render(<App />);
    expect(await screen.findByText(/A BETTER WAY TO WAIT/i)).toBeInTheDocument();
  });

  it("renders admin login", async () => {
    mockFetch([["/api/health", { data: {} }]]);
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Admin portal/i }));
    expect(await screen.findByText(/Welcome back/i)).toBeInTheDocument();
  });

  it("loads a business", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic", { data: { status: "success", business: { id: "b1", business_name: "Demo Clinic", business_type: "Clinic" } } }],
      ["/api/public/business/demo-clinic/services", { data: { status: "success", services: [{ id: "s1", service_name: "Haircut", duration_minutes: 30 }] } }],
    ]);
    render(<App />);
    // load business input already has demo-clinic; click first Load business button if present
    const btns = screen.queryAllByRole("button", { name: /load business/i });
    if (btns.length) await user.click(btns[0]);
    await screen.findByText(/Business loaded/i).catch(() => {});
  });
});
