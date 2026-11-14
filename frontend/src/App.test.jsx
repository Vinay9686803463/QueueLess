import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

describe("QueueLess frontend", () => {
  let user;

  beforeEach(() => {
    user = userEvent.setup();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("shows backend status and the customer login on a fresh session", async () => {
    localStorage.setItem("queueless_token", "old-admin-token");
    localStorage.setItem("queueless_customer_token", "old-customer-token");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(await screen.findByText(/System online/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(localStorage.getItem("queueless_token")).toBeNull();
      expect(localStorage.getItem("queueless_customer_token")).toBeNull();
    });
    expect(screen.queryByText(/A BETTER WAY TO WAIT/i)).not.toBeInTheDocument();
  });

  it("registers customers, loads their history, and books an appointment with their token", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/customer-auth/register")) {
        expect(JSON.parse(options.body)).toMatchObject({
          full_name: "Taylor Customer",
          email: "taylor@example.com",
          phone: "555-0101",
          password: "password123",
        });
        expect(options.headers.Authorization).toBeUndefined();
        return jsonResponse({ access_token: "customer-token" }, 201);
      }
      if (requestUrl.includes("/api/customer-auth/appointments")) {
        expect(options.headers.Authorization).toBe("Bearer customer-token");
        return jsonResponse({
          appointments: [{
            id: "appointment-1",
            service_name: "Consultation",
            status: "confirmed",
            scheduled_at: "2027-01-02T10:00:00",
          }],
        });
      }
      if (requestUrl.includes("/api/customer-auth/queue-tokens")) {
        expect(options.headers.Authorization).toBe("Bearer customer-token");
        return jsonResponse({
          tokens: [{ id: "token-1", token_number: 14, status: "waiting", ahead: 2 }],
        });
      }
      if (requestUrl.includes("/api/public/business/demo-clinic/services")) {
        expect(options.headers.Authorization).toBeUndefined();
        return jsonResponse({
          services: [{ id: "service-1", service_name: "Consultation", duration_minutes: 30 }],
        });
      }
      if (requestUrl.includes("/api/public/business/demo-clinic")) {
        return jsonResponse({
          business: { id: "business-1", business_name: "Demo Clinic" },
        });
      }
      if (requestUrl.includes("/api/public/bookings")) {
        expect(options.headers.Authorization).toBe("Bearer customer-token");
        expect(JSON.parse(options.body)).toMatchObject({
          service_id: "service-1",
          customer_name: "Taylor Customer",
          customer_email: "taylor@example.com",
        });
        return jsonResponse({
          appointment: { id: "appointment-2" },
          estimated_wait_minutes: 10,
        }, 201);
      }
      if (requestUrl.includes("/api/public/track/track-code")) {
        expect(options.headers.Authorization).toBeUndefined();
        return jsonResponse({
          tracking: {
            token_number: 14,
            queue_status: "waiting",
            customers_ahead: 2,
            estimated_wait_minutes: 10,
          },
        });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Create customer account" }));
    await user.type(screen.getByLabelText("Full name"), "Taylor Customer");
    await user.type(screen.getByLabelText("Phone number"), "555-0101");
    await user.type(screen.getByLabelText("Email address"), "taylor@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Register/ }));

    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    expect(await screen.findByText(/Consultation · confirmed/)).toBeInTheDocument();
    expect(await screen.findByText(/Token #14 · waiting · 2 ahead/)).toBeInTheDocument();
    expect(localStorage.getItem("queueless_customer_token")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Load" }));
    await user.selectOptions(screen.getByLabelText("Select service"), "service-1");
    await user.type(screen.getByLabelText("Appointment date and time"), "2027-01-02T10:00");
    await user.click(screen.getByRole("button", { name: /Continue to check-in/i }));

    expect(await screen.findByText(/Appointment ID: appointment-2/)).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Enter tracking code"), "track-code");
    await user.click(screen.getByRole("button", { name: "Track token" }));
    expect(await screen.findByText("YOUR TOKEN")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalled();
  });

  it("logs customers in without using legacy or admin tokens and supports logout", async () => {
    localStorage.setItem("queueless_token", "legacy-admin-token");
    localStorage.setItem("queueless_customer_token", "legacy-customer-token");
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/customer-auth/login")) {
        expect(options.headers.Authorization).toBeUndefined();
        return jsonResponse({ access_token: "current-customer-token" });
      }
      if (requestUrl.includes("/api/customer-auth/appointments")) {
        expect(options.headers.Authorization).toBe("Bearer current-customer-token");
        return jsonResponse({ appointments: [] });
      }
      if (requestUrl.includes("/api/customer-auth/queue-tokens")) {
        expect(options.headers.Authorization).toBe("Bearer current-customer-token");
        return jsonResponse({ tokens: [] });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    const firstRender = render(<App />);
    await user.type(screen.getByLabelText("Email address"), "taylor@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to customer portal/ }));

    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    expect(localStorage.getItem("queueless_token")).toBeNull();
    expect(localStorage.getItem("queueless_customer_token")).toBeNull();
    expect(fetch).toHaveBeenCalled();

    firstRender.unmount();
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Email address"), "taylor@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to customer portal/ }));
    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Logout" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("switches to an independent admin portal, supports logout, and remembers the portal across refresh", async () => {
    localStorage.setItem("queueless_customer_token", "legacy-customer-token");
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/customer-auth/login")) {
        expect(options.headers.Authorization).toBeUndefined();
        return jsonResponse({ access_token: "customer-session-token" });
      }
      if (requestUrl.includes("/api/customer-auth/appointments")) {
        expect(options.headers.Authorization).toBe("Bearer customer-session-token");
        return jsonResponse({ appointments: [] });
      }
      if (requestUrl.includes("/api/customer-auth/queue-tokens")) {
        expect(options.headers.Authorization).toBe("Bearer customer-session-token");
        return jsonResponse({ tokens: [] });
      }
      if (requestUrl.includes("/api/auth/login")) {
        expect(options.headers.Authorization).toBeUndefined();
        return jsonResponse({ access_token: "admin-session-token" });
      }
      if (requestUrl.includes("/api/businesses")) {
        expect(options.headers.Authorization).toBe("Bearer admin-session-token");
        return jsonResponse({ businesses: [] });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    const firstRender = render(<App />);
    await user.type(screen.getByLabelText("Email address"), "customer@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to customer portal/ }));
    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    expect(await screen.findByText(/ADMINISTRATOR ACCESS/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email address"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to dashboard/i }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/businesses"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer admin-session-token" }),
      })
    ));
    expect(localStorage.getItem("queueless_token")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Switch to Customer Portal" }));
    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Logout" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Email address"));
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Email address"), "customer@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to customer portal/ }));
    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();

    firstRender.unmount();
    render(<App />);
    expect(await screen.findByText(/ADMINISTRATOR ACCESS/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(sessionStorage.getItem("queueless_portal")).toBe("admin");

    await user.type(screen.getByLabelText("Email address"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to dashboard/i }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Logout" }));
    expect(await screen.findByText(/ADMINISTRATOR ACCESS/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch to Customer Portal" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("preserves admin registration", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      if (String(url).includes("/api/auth/register")) {
        expect(JSON.parse(options.body)).toMatchObject({
          full_name: "Admin User",
          email: "admin@example.com",
          password: "password123",
        });
        return jsonResponse({ access_token: "registered-admin-token" }, 201);
      }
      if (String(url).includes("/api/businesses")) {
        expect(options.headers.Authorization).toBe("Bearer registered-admin-token");
        return jsonResponse({ businesses: [] });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await user.type(screen.getByPlaceholderText("Full name"), "Admin User");
    await user.type(screen.getByPlaceholderText("Email"), "admin@example.com");
    await user.type(screen.getByPlaceholderText("Password"), "password123");
    await user.type(screen.getByPlaceholderText("Confirm password"), "password123");
    await user.click(screen.getByRole("button", { name: "Register" }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });
});
