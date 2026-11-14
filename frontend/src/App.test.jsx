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

  it.each([
    ["admin", "incorrect email", "unknown-admin@example.com", "password123", "/api/auth/login"],
    ["admin", "incorrect password", "admin@example.com", "wrong-password", "/api/auth/login"],
    ["customer", "incorrect email", "unknown-customer@example.com", "password123", "/api/customer-auth/login"],
    ["customer", "incorrect password", "customer@example.com", "wrong-password", "/api/customer-auth/login"],
  ])("shows an inline error for %s %s and clears it when corrected", async (portal, _caseName, loginEmail, loginPassword, endpoint) => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      return jsonResponse({ message: "Invalid email or password" }, 401);
    });

    render(<App />);
    if (portal === "admin") {
      await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    }

    await user.type(screen.getByLabelText("Email address"), loginEmail);
    await user.type(screen.getByLabelText("Password"), loginPassword);
    await user.click(screen.getByRole("button", {
      name: portal === "admin" ? /Sign in to dashboard/ : /Sign in to customer portal/,
    }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("Invalid email or password.");
    expect(error).toHaveClass("login-error");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(endpoint),
      expect.objectContaining({
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      })
    );
    expect(screen.queryByRole("heading", { name: "Dashboard" })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Password"), "1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each(["admin", "customer"])("%s login prevents duplicate submissions and shows loading", async (portal) => {
    let finishLogin;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      if (String(url).includes("/api/health")) return Promise.resolve(jsonResponse({}));
      return new Promise((resolve) => {
        finishLogin = () => resolve(jsonResponse({ message: "Invalid email or password" }, 401));
      });
    });

    render(<App />);
    if (portal === "admin") {
      await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    }
    await user.type(screen.getByLabelText("Email address"), `${portal}@example.com`);
    await user.type(screen.getByLabelText("Password"), "wrong-password");

    const submit = screen.getByRole("button", {
      name: portal === "admin" ? /Sign in to dashboard/ : /Sign in to customer portal/,
    });
    await user.click(submit);

    const loadingButton = await screen.findByRole("button", { name: /Signing in/ });
    expect(loadingButton).toBeDisabled();
    await user.click(loadingButton);
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/login"))).toHaveLength(1);

    finishLogin();
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });

  it("shows meaningful backend login errors to the user", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      return jsonResponse({ message: "Too many login attempts. Please try again later." }, 429);
    });

    render(<App />);
    await user.type(screen.getByLabelText("Email address"), "customer@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to customer portal/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many login attempts. Please try again later."
    );
  });

  it.each([
    ["admin", "sollapurevinay17@gmail.com", "/api/auth/login"],
    ["customer", "vinayssollapure@gmail.com", "/api/customer-auth/login"],
  ])("keeps the %s email confined to its own authentication route", async (portal, email, endpoint) => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      return jsonResponse({ message: "Invalid email or password" }, 401);
    });

    render(<App />);
    if (portal === "admin") {
      await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    }

    await user.type(screen.getByLabelText("Email address"), email);
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", {
      name: portal === "admin" ? /Sign in to dashboard/ : /Sign in to customer portal/,
    }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(endpoint),
      expect.objectContaining({ method: "POST" })
    );
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/login"))).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "Dashboard" })).not.toBeInTheDocument();
  });

  it("uses the same login layout and card styling for both portals", async () => {
    render(<App />);
    const customerPage = screen.getByRole("main");
    expect(customerPage).toHaveClass("login-page");
    expect(customerPage.querySelector(".login-card")).toHaveClass("customer-login-card");
    expect(customerPage.querySelector(".login-art")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    const adminPage = screen.getByRole("main");
    expect(adminPage).toHaveClass("login-page");
    expect(adminPage.querySelector(".login-card")).toHaveClass("login-card");
    expect(adminPage.querySelector(".login-art")).toBeInTheDocument();
  });

  it("shows Forgot Password actions in both portals without changing registration", async () => {
    render(<App />);
    const customerActions = screen.getByRole("button", {
      name: "Create customer account",
    }).parentElement;
    expect(customerActions).toHaveClass("login-secondary-actions");
    expect(customerActions).toContainElement(screen.getByRole("button", { name: "Forgot password" }));
    await user.click(screen.getByRole("button", { name: "Forgot password" }));
    expect(screen.getByRole("heading", { name: "Forgot Password" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to customer login" }));

    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    const adminCreateAccount = screen.getByRole("button", { name: "Create account" });
    const adminActions = adminCreateAccount.parentElement;
    expect(adminActions).toHaveClass("login-secondary-actions");
    expect(adminActions).toContainElement(screen.getByRole("button", { name: "Forgot password" }));

    await user.click(adminCreateAccount);
    expect(screen.getByPlaceholderText("Full name")).toBeInTheDocument();
  });

  it.each([
    {
      portal: "customer",
      email: "customer@example.com",
      prefix: "customer-auth",
    },
    {
      portal: "admin",
      email: "admin@example.com",
      prefix: "auth",
    },
  ])("completes the $portal forgot-password flow and signs in with the new password", async ({
    portal,
    email,
    prefix,
  }) => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      const body = options.body ? JSON.parse(options.body) : {};
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes(`/api/${prefix}/forgot-password`)) {
        expect(body.email).toBe(email);
        return jsonResponse({
          status: "success",
          message: "If the email matches an active account in this portal, a verification code will be sent.",
        }, 202);
      }
      if (requestUrl.includes(`/api/${prefix}/verify-otp`)) {
        expect(body).toEqual({ email, otp: "123456" });
        return jsonResponse({ reset_token: "one-time-reset-authorization" });
      }
      if (requestUrl.includes(`/api/${prefix}/reset-password`)) {
        expect(body).toEqual({
          token: "one-time-reset-authorization",
          password: "new-password-123",
        });
        return jsonResponse({ status: "success" });
      }
      if (requestUrl.includes(`/api/${prefix}/login`)) {
        expect(body).toEqual({ email, password: "new-password-123" });
        return jsonResponse({ access_token: `${portal}-access-token` });
      }
      if (requestUrl.includes("/api/customer-auth/appointments")) {
        return jsonResponse({ appointments: [] });
      }
      if (requestUrl.includes("/api/customer-auth/queue-tokens")) {
        return jsonResponse({ tokens: [] });
      }
      if (requestUrl.includes("/api/businesses")) {
        return jsonResponse({ businesses: [] });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    if (portal === "admin") {
      await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    }

    const emailInput = screen.getByLabelText("Email address");
    await user.type(emailInput, email);
    await user.click(screen.getByRole("button", { name: "Forgot password" }));
    await user.clear(screen.getByLabelText("Registered email address"));
    await user.type(screen.getByLabelText("Registered email address"), email);
    await user.click(screen.getByRole("button", { name: "Send OTP" }));

    expect(await screen.findByText(/If the email matches an active account in this portal, a verification code will be sent/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Resend OTP in 60s/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify OTP" }));

    await user.type(await screen.findByLabelText("New Password"), "new-password-123");
    await user.type(screen.getByLabelText("Confirm Password"), "mismatch-123");
    await user.click(screen.getByRole("button", { name: "Change your password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The passwords do not match.");
    expect(fetch.mock.calls.some(([url]) => String(url).includes(`/api/${prefix}/reset-password`))).toBe(false);

    await user.clear(screen.getByLabelText("Confirm Password"));
    await user.type(screen.getByLabelText("Confirm Password"), "new-password-123");
    await user.click(screen.getByRole("button", { name: "Change your password" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Your password has been changed successfully! Please log in with your new password."
    );
    await user.click(screen.getByRole("button", { name: "OK" }));
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Password"), "new-password-123");
    await user.click(screen.getByRole("button", {
      name: portal === "admin" ? /Sign in to dashboard/ : /Sign in to customer portal/,
    }));
    if (portal === "admin") {
      expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    } else {
      expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    }

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/${prefix}/reset-password`),
      expect.any(Object)
    );
  });

  it("shows SMTP delivery configuration errors without claiming an OTP was sent", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      if (String(url).includes("/api/customer-auth/forgot-password")) {
        return jsonResponse({
          status: "error",
          message: "Password reset email is not configured. Contact the system administrator.",
        }, 503);
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Forgot password" }));
    await user.type(screen.getByLabelText("Registered email address"), "customer@example.com");
    await user.click(screen.getByRole("button", { name: "Send OTP" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password reset email is not configured. Contact the system administrator."
    );
    expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();
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
