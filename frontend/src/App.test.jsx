import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

function mockAdminApi({
  businesses = [],
  queues = {},
  services = {},
  appointments = [],
} = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const requestUrl = String(url);
    if (requestUrl.includes("/api/health")) return jsonResponse({});
    if (requestUrl.includes("/api/auth/login")) {
      return jsonResponse({ access_token: "admin-session-token" });
    }
    if (requestUrl.endsWith("/api/businesses")) {
      return jsonResponse({ status: "success", count: businesses.length, businesses });
    }

    const serviceMatch = requestUrl.match(/\/api\/businesses\/([^/?]+)\/services$/);
    if (serviceMatch) {
      return jsonResponse({ services: services[serviceMatch[1]] || [] });
    }
    const queueMatch = requestUrl.match(/\/api\/businesses\/([^/?]+)\/queue(?:\?|$)/);
    if (queueMatch) {
      const response = queues[queueMatch[1]];
      return typeof response === "function"
        ? response()
        : jsonResponse(response || { waiting: [] });
    }
    if (requestUrl.includes("/api/appointments")) {
      return jsonResponse({ appointments });
    }
    return jsonResponse({ message: "not found" }, 404);
  });
}

async function signInAsAdmin(user) {
  await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
  await user.type(screen.getByLabelText("Email address"), "admin@example.com");
  await user.type(screen.getByLabelText("Password"), "password123");
  await user.click(screen.getByRole("button", { name: /Sign in to dashboard/ }));
  await screen.findByRole("heading", { name: "Dashboard" });
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

  it("matches the customer login copy and supports password visibility", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    render(<App />);

    expect(await screen.findByText("CUSTOMER PORTAL")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByText("Sign in to book visits and track your place in line.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("placeholder", "customer@example.com");
    expect(screen.getByRole("button", { name: "Sign in to customer portal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create customer account" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Forgot password" })).toBeInTheDocument();

    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
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
      if (requestUrl.includes("/api/public/businesses/" ) && requestUrl.endsWith("/services")) {
        return jsonResponse({ services: [{ id: "service-1", service_name: "Consultation", duration_minutes: 30, price: 0 }] });
      }
      if (requestUrl.includes("/api/public/businesses")) {
        return jsonResponse({ businesses: [{ id: "business-1", business_name: "Pioneer Community Bank", business_type: "Clinic", is_active: true }] });
      }
      if (requestUrl.includes("/api/public/availability")) {
        return jsonResponse({ slots: [{ start: "2027-01-02T10:00:00Z", end: "2027-01-02T11:00:00Z", label: "10:00 AM – 11:00 AM" }] });
      }
      if (requestUrl.includes("/api/public/business/demo-clinic") || requestUrl.includes("/api/public/business/business-1")) {
        return jsonResponse({
          business: { id: "business-1", business_name: "Pioneer Community Bank" },
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
    expect(localStorage.getItem("queueless_customer_token")).toBe("customer-token");

    await user.selectOptions(screen.getByLabelText("Choose a business"), "business-1");
    await user.selectOptions(screen.getByLabelText("Select service"), "service-1");
    await user.type(screen.getByLabelText("Available appointment date"), "2027-01-02");
    await user.selectOptions(await screen.findByLabelText(/Available time/), "2027-01-02T10:00:00Z");
    await user.click(screen.getByRole("button", { name: /Continue to check-in/i }));

    expect(await screen.findByText(/Appointment ID: appointment-2/)).toBeInTheDocument();
    expect(screen.getByText(/Appointment time:/)).toBeInTheDocument();
    expect(screen.queryByText(/Estimated wait: To be confirmed/)).not.toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Enter tracking code or appointment ID"), "track-code");
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
      if (requestUrl.includes("/api/auth/me")) {
        return jsonResponse({ message: "Invalid token" }, 401);
      }
      if (requestUrl.includes("/api/customer-auth/me")) {
        if (options.headers.Authorization === "Bearer current-customer-token") {
          return jsonResponse({
            customer: {
              full_name: "Taylor Customer",
              email: "taylor@example.com",
            },
          });
        }
        return jsonResponse({ message: "Invalid token" }, 401);
      }
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
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email address"), "taylor@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to customer portal/ }));

    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    expect(localStorage.getItem("queueless_token")).toBeNull();
    expect(localStorage.getItem("queueless_customer_token")).toBe("current-customer-token");
    expect(fetch).toHaveBeenCalled();

    firstRender.unmount();
    render(<App />);
    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(screen.getByRole("button", { name: "Log out" }));
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
    const customerCard = customerPage.querySelector(".login-card");
    expect(customerCard).toHaveClass("customer-login-card");
    expect(customerPage.querySelector(".login-art")).toBeInTheDocument();
    expect(screen.getByText("CUSTOMER PORTAL")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByText("Sign in to book visits and track your place in line.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("placeholder", "customer@example.com");
    const customerPassword = screen.getByLabelText("Password");
    expect(customerPassword).toHaveAttribute("placeholder", "Enter your password");
    expect(customerPassword).toHaveValue("");
    expect(customerCard.querySelector(".login-password-field")).toBeInTheDocument();
    expect(customerCard.querySelector(".login-password-toggle")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(customerPassword).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(customerPassword).toHaveAttribute("type", "password");
    await user.type(customerPassword, "secret123");
    expect(customerPassword).toHaveValue("secret123");

    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    const adminPage = screen.getByRole("main");
    expect(adminPage).toHaveClass("login-page");
    const adminCard = adminPage.querySelector(".login-card");
    expect(adminCard).toHaveClass("login-card");
    expect(adminPage.querySelector(".login-art")).toBeInTheDocument();
    expect(adminCard.querySelector(".login-password-field")).toBeInTheDocument();
    expect(adminCard.querySelector(".login-password-toggle")).toBeInTheDocument();
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
          email_sent: true,
          message: "A verification code was sent. Check your inbox.",
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

    expect(await screen.findByText(/Enter the six-digit code sent to/)).toBeInTheDocument();
    expect(screen.getByText(email, { selector: "strong" })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
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
          message: "Gmail did not accept the recipient address. Check the account email and try again.",
        }, 503);
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Forgot password" }));
    await user.type(screen.getByLabelText("Registered email address"), "customer@example.com");
    await user.click(screen.getByRole("button", { name: "Send OTP" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Gmail did not accept the recipient address. Check the account email and try again."
    );
    expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();
  });

  it("selects Pioneer Community Bank by exact name when it exists", async () => {
    const businesses = [
      { id: "pioneer-db-id-42", business_name: "Pioneer Community Bank" },
      { id: "vinay-db-id-17", business_name: "Vinay Clinic" },
    ];
    const fetch = mockAdminApi({ businesses });

    render(<App />);
    await signInAsAdmin(user);

    const selector = await screen.findByLabelText("Current business");
    await waitFor(() => expect(selector).toHaveValue("pioneer-db-id-42"));
    expect([...selector.options].map((option) => option.textContent)).toEqual([
      "Select business",
      "Pioneer Community Bank",
      "Vinay Clinic",
    ]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/demo"))).toBe(false);
  });

  it("falls back to Vinay Clinic and keeps the dashboard usable when Pioneer is absent", async () => {
    const fetch = mockAdminApi({
      businesses: [{ id: "vinay-db-id-17", business_name: "Vinay Clinic" }],
      queues: {
        "vinay-db-id-17": {
          waiting: [{
            id: "vinay-queue-1",
            token_number: 1,
            customer_name: "Vinay Customer",
            service_name: "Consultation",
            status: "waiting",
          }],
        },
      },
      services: {
        "vinay-db-id-17": [{
          id: "vinay-service-1",
          service_name: "Vinay Consultation",
          is_active: true,
        }],
      },
    });

    render(<App />);
    await signInAsAdmin(user);

    expect(await screen.findByLabelText("Current business")).toHaveValue("vinay-db-id-17");
    expect(await screen.findByText(
      "Pioneer Community Bank is unavailable. Showing Vinay Clinic instead.",
      { selector: ".business-availability-notice" }
    )).toBeInTheDocument();
    expect(await screen.findByText("Vinay Customer")).toBeInTheDocument();
    expect(await screen.findByText("Vinay Consultation")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Businesses could not be loaded" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/api/businesses/vinay-db-id-17/queue?"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/api/businesses/vinay-db-id-17/services"))).toBe(true);
  });

  it("keeps every API business available in the selector", async () => {
    const businesses = [
      { id: "pioneer-id", business_name: "Pioneer Community Bank" },
      { id: "vinay-id", business_name: "Vinay Clinic" },
      { id: "another-id", business_name: "Another Clinic" },
    ];
    mockAdminApi({ businesses });

    render(<App />);
    await signInAsAdmin(user);

    const selector = await screen.findByLabelText("Current business");
    await waitFor(() => expect(selector).toHaveValue("pioneer-id"));
    expect([...selector.options].slice(1).map((option) => option.textContent)).toEqual(
      businesses.map((business) => business.business_name)
    );
  });

  it("reloads queue, services, and appointments for the newly selected business", async () => {
    const businesses = [
      { id: "business-one", business_name: "Pioneer Community Bank" },
      { id: "business-two", business_name: "Vinay Clinic" },
    ];
    const fetch = mockAdminApi({
      businesses,
      queues: {
        "business-one": { waiting: [{
          id: "queue-one",
          token_number: 1,
          customer_name: "First Business Customer",
          service_name: "First Service",
          status: "waiting",
        }] },
        "business-two": { waiting: [{
          id: "queue-two",
          token_number: 2,
          customer_name: "Second Business Customer",
          service_name: "Second Service",
          status: "waiting",
        }] },
      },
      services: {
        "business-one": [{ id: "service-one", service_name: "First Business Service", is_active: true }],
        "business-two": [{ id: "service-two", service_name: "Second Business Service", is_active: true }],
      },
      appointments: [
        {
          id: "appointment-past",
          business_id: "business-one",
          customer_name: "Past Business Appointment",
          service_name: "Past Appointment Service",
          status: "confirmed",
          scheduled_at: "2020-01-02T10:00:00",
        },
        {
          id: "appointment-one",
          business_id: "business-one",
          customer_name: "First Business Appointment",
          service_name: "First Appointment Service",
          status: "confirmed",
          scheduled_at: "2027-01-02T10:00:00",
        },
        {
          id: "appointment-two",
          business_id: "business-two",
          customer_name: "Second Business Appointment",
          service_name: "Second Appointment Service",
          status: "confirmed",
          scheduled_at: "2027-01-02T11:00:00",
        },
      ],
    });

    render(<App />);
    await signInAsAdmin(user);
    const selector = await screen.findByLabelText("Current business");
    expect(await screen.findByText("First Business Customer")).toBeInTheDocument();
    expect(await screen.findByText("First Business Service")).toBeInTheDocument();
    expect(await screen.findByText(/First Appointment Service · First Business Appointment/)).toBeInTheDocument();
    expect(await screen.findByText(/Past Appointment Service · Past Business Appointment/)).toBeInTheDocument();
    expect(
      screen.getByText("Upcoming appointments").closest(".stat-card").querySelector("strong")
    ).toHaveTextContent("1");

    await user.selectOptions(selector, "business-two");

    expect(await screen.findByText("Second Business Customer")).toBeInTheDocument();
    expect(await screen.findByText("Second Business Service")).toBeInTheDocument();
    expect(await screen.findByText(/Second Appointment Service · Second Business Appointment/)).toBeInTheDocument();
    expect(screen.queryByText("First Business Customer")).not.toBeInTheDocument();
    expect(screen.queryByText("First Business Service")).not.toBeInTheDocument();
    expect(screen.queryByText(/First Appointment Service · First Business Appointment/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Past Appointment Service · Past Business Appointment/)).not.toBeInTheDocument();
    expect(
      screen.getByText("Upcoming appointments").closest(".stat-card").querySelector("strong")
    ).toHaveTextContent("1");
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/api/businesses/business-two/queue?"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/api/businesses/business-two/services"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) =>
      String(url).includes("/api/appointments?business_id=business-two")
    )).toBe(true);
  });

  it("shows appointment retrieval failures instead of reporting zero and retries successfully", async () => {
    let appointmentRequests = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/auth/login")) {
        return jsonResponse({ access_token: "admin-session-token" });
      }
      if (requestUrl.endsWith("/api/businesses")) {
        return jsonResponse({
          businesses: [{ id: "business-one", business_name: "Pioneer Community Bank" }],
        });
      }
      if (requestUrl.includes("/api/businesses/business-one/services")) {
        return jsonResponse({ services: [] });
      }
      if (requestUrl.includes("/api/businesses/business-one/queue")) {
        return jsonResponse({ waiting: [] });
      }
      if (requestUrl.includes("/api/appointments?business_id=business-one")) {
        appointmentRequests += 1;
        if (appointmentRequests === 1) {
          return jsonResponse({
            status: "error",
            message: "Unable to retrieve appointments",
          }, 500);
        }
        return jsonResponse({
          appointments: [{
            id: "appointment-one",
            business_id: "business-one",
            customer_name: "Recovered Appointment",
            service_name: "Consultation",
            status: "confirmed",
            scheduled_at: "2027-01-02T10:00:00",
          }],
        });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await signInAsAdmin(user);

    expect(await screen.findByText(
      "Appointments could not be loaded: Unable to retrieve appointments"
    )).toBeInTheDocument();
    expect(
      screen.getByText("Upcoming appointments").closest(".stat-card").querySelector("strong")
    ).toHaveTextContent("—");
    expect(screen.queryByText("No appointments are scheduled for this business.")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(/Consultation · Recovered Appointment/)).toBeInTheDocument();
    expect(appointmentRequests).toBe(2);
  });

  it("shows a no-businesses state for a successful empty API response", async () => {
    mockAdminApi({ businesses: [] });

    render(<App />);
    await signInAsAdmin(user);

    expect(await screen.findByRole("heading", { name: "No business configured" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Businesses could not be loaded" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("ignores an old business response that completes after switching businesses", async () => {
    let resolveOldQueue;
    const oldQueueResponse = new Promise((resolve) => {
      resolveOldQueue = () => resolve(jsonResponse({
        waiting: [{
          id: "old-queue",
          token_number: 1,
          customer_name: "Old Business Customer",
          service_name: "Old Service",
          status: "waiting",
        }],
      }));
    });
    mockAdminApi({
      businesses: [
        { id: "business-one", business_name: "Pioneer Community Bank" },
        { id: "business-two", business_name: "Vinay Clinic" },
      ],
      queues: {
        "business-one": () => oldQueueResponse,
        "business-two": { waiting: [{
          id: "current-queue",
          token_number: 2,
          customer_name: "Current Business Customer",
          service_name: "Current Service",
          status: "waiting",
        }] },
      },
    });

    render(<App />);
    await signInAsAdmin(user);
    const selector = await screen.findByLabelText("Current business");
    await waitFor(() => expect(selector).toHaveValue("business-one"));
    await user.selectOptions(selector, "business-two");

    expect(await screen.findByText("Current Business Customer")).toBeInTheDocument();
    resolveOldQueue();
    await waitFor(() => expect(screen.queryByText("Old Business Customer")).not.toBeInTheDocument());
    expect(screen.getByText("Current Business Customer")).toBeInTheDocument();
  });

  it("shows a business API error instead of the no-business empty state", async () => {
    let businessListRequests = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/auth/login")) {
        return jsonResponse({ access_token: "admin-session-token" });
      }
      if (requestUrl.endsWith("/api/businesses")) {
        businessListRequests += 1;
        expect(options.headers.Authorization).toBe("Bearer admin-session-token");
        if (businessListRequests === 1) {
          return jsonResponse({
            status: "error",
            message: "Business list temporarily unavailable",
          }, 500);
        }
        return jsonResponse({ status: "success", businesses: [] });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    await user.type(screen.getByLabelText("Email address"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to dashboard/ }));

    expect(await screen.findByRole("heading", {
      name: "Businesses could not be loaded",
    })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Business list temporarily unavailable"
    );
    expect(screen.queryByRole("heading", { name: "No business configured" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/businesses"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer admin-session-token",
        }),
      })
    );

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "No business configured" })).toBeInTheDocument();
    expect(businessListRequests).toBe(2);
  });

  it("does not enter OTP verification unless email delivery is confirmed", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).includes("/api/health")) return jsonResponse({});
      if (String(url).includes("/api/customer-auth/forgot-password")) {
        return jsonResponse({
          status: "accepted",
          email_sent: false,
          message: "If the email matches an active account in this portal, a verification code will be sent.",
        }, 202);
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Forgot password" }));
    await user.type(
      screen.getByLabelText("Registered email address"),
      "customer@example.com"
    );
    await user.click(screen.getByRole("button", { name: "Send OTP" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to send a verification code."
    );
    expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Registered email address")).toHaveValue("customer@example.com");
    expect(screen.getByRole("button", { name: "Send OTP" })).toBeEnabled();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/verify-otp"))).toBe(false);
  });

  it("switches to an independent admin portal, supports logout, and remembers the portal across refresh", async () => {
    localStorage.setItem("queueless_customer_token", "legacy-customer-token");
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/auth/me")) {
        return jsonResponse({ message: "Invalid token" }, 401);
      }
      if (requestUrl.includes("/api/customer-auth/me")) {
        return jsonResponse({ message: "Invalid token" }, 401);
      }
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
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
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
    expect(localStorage.getItem("queueless_token")).toBe("admin-session-token");

    await user.click(screen.getByRole("button", { name: "Switch to Customer Portal" }));
    expect(await screen.findByText(/You’re signed in/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(screen.getByRole("button", { name: "Log out" }));
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
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByText(/ADMINISTRATOR ACCESS/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch to Customer Portal" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("renders admin queue, schedule, activity and service management and refreshes after actions", async () => {
    let paused = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options = {}) => {
      const requestUrl = String(url);
      if (requestUrl.includes("/api/health")) return jsonResponse({});
      if (requestUrl.includes("/api/auth/login")) {
        return jsonResponse({ access_token: "admin-session-token" });
      }
      if (requestUrl.endsWith("/api/businesses")) {
        return jsonResponse({
          businesses: [{ id: "business-1", business_name: "Pioneer Community Bank" }],
        });
      }
      if (requestUrl.includes("/api/businesses/business-1/services")) {
        if (options.method === "PUT" || options.method === "POST") {
          return jsonResponse({ status: "success" });
        }
        return jsonResponse({
          services: [{
            id: "service-1",
            service_name: "Consultation",
            description: "General appointment",
            duration_minutes: 30,
            price: 25,
            is_active: true,
          }],
        });
      }
      if (requestUrl.includes("/api/businesses/business-1/queue/demo")) {
        return jsonResponse({
          status: "success",
          message: options.method === "DELETE"
            ? "Removed 12 demo queue entries."
            : "Created 12 demo queue entries.",
        });
      }
      if (requestUrl.endsWith("/api/businesses/business-1/queue/pause")) {
        paused = true;
        return jsonResponse({ status: "success", queue_paused: true });
      }
      if (requestUrl.endsWith("/api/businesses/business-1/queue/resume")) {
        paused = false;
        return jsonResponse({ status: "success", queue_paused: false });
      }
      if (requestUrl.includes("/api/businesses/business-1/queue")) {
        if (options.method === "POST") return jsonResponse({ status: "success" });
        return jsonResponse({
          queue_paused: paused,
          waiting: [{ id: "waiting-1", token_number: 4, customer_name: "Waiting Customer", status: "waiting" }],
          called: [{ id: "called-1", token_number: 3, customer_name: "Serving Customer", status: "called" }],
          completed: [],
          skipped: [],
          cancelled: [],
        });
      }
      if (requestUrl.includes("/api/appointments")) {
        if (options.method === "DELETE") return jsonResponse({ status: "success" });
        return jsonResponse({
          appointments: [{
            id: "appointment-1",
            business_id: "business-1",
            customer_name: "Scheduled Customer",
            customer_phone: "555-0100",
            service_name: "Consultation",
            status: "confirmed",
            scheduled_at: "2027-01-02T10:00:00",
          }],
        });
      }
      return jsonResponse({ message: "not found" }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: "Switch to Admin Portal" }));
    await user.type(screen.getByLabelText("Email address"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /Sign in to dashboard/ }));

    expect(await screen.findByRole("link", { name: "Queue Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Digital Queue" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Schedule" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Real-Time Activity" })).toBeInTheDocument();
    expect(await screen.findByText(/Waiting Customer/)).toBeInTheDocument();
    expect(await screen.findByText(/Serving Customer/)).toBeInTheDocument();
    expect(await screen.findAllByText(/Scheduled Customer/)).toHaveLength(3);

    const waitForRequest = (path, method = "POST") =>
      waitFor(() => expect(fetch.mock.calls.some(
        ([url, options]) => String(url).includes(path) && options.method === method
      ), `Expected ${method} request containing ${path}`).toBe(true));
    const waitForQueueIdle = () =>
      waitFor(() => expect(
        screen.getAllByRole("button", { name: "Skip", exact: true })[0]
      ).toBeEnabled());

    await user.click(screen.getByRole("button", { name: "Complete Service" }));
    await waitForRequest("/queue/called-1/complete");
    await waitForQueueIdle();
    await user.click(screen.getAllByRole("button", { name: "Skip", exact: true })[0]);
    await waitForRequest("/queue/waiting-1/skip");
    await waitForQueueIdle();
    await user.click(screen.getAllByRole("button", { name: "Cancel Entry", exact: true })[0]);
    await waitForRequest("/queue/called-1/cancel");
    await waitForQueueIdle();
    await user.click(screen.getAllByRole("button", { name: "Cancel", exact: true })[0]);
    await waitForRequest("/queue/waiting-1/cancel");
    await waitForQueueIdle();
    await user.click(screen.getAllByRole("button", { name: "Cancel", exact: true }).at(-1));
    await waitForRequest("/appointments/appointment-1", "DELETE");
    await user.click(screen.getAllByRole("button", { name: "Pause Queue" })[0]);
    await waitForRequest("/queue/pause");
    await user.click((await screen.findAllByRole("button", { name: "Resume Queue" }))[0]);
    await waitForRequest("/queue/resume");
    await user.click(screen.getAllByRole("button", { name: "Call Next Customer", exact: true })[0]);
    await waitForRequest("/queue/call-next");
    await user.click(screen.getByRole("button", { name: "Remove Demo Entries" }));
    await waitForRequest("/queue/demo", "DELETE");
    await user.type(screen.getByLabelText("Service name"), "New service");
    await user.click(screen.getByRole("button", { name: "Add service" }));
    await waitForRequest("/services", "POST");
    await waitForRequest("/queue/demo");
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitForRequest("/services/service-1", "PUT");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Save service" }));
    await waitFor(() => expect(fetch.mock.calls.filter(
      ([url, options]) => String(url).includes("/services/service-1") && options.method === "PUT"
    ).length).toBeGreaterThan(1));

    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/called-1/complete"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/waiting-1/skip"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/called-1/cancel"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/waiting-1/cancel"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/pause"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/resume"))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/queue/call-next"))).toBe(true);
    expect(fetch.mock.calls.some(([url, options]) => String(url).includes("/queue/demo") && options.method === "POST")).toBe(true);
    expect(fetch.mock.calls.some(([url, options]) => String(url).includes("/queue/demo") && options.method === "DELETE")).toBe(true);
    expect(fetch.mock.calls.some(([url, options]) => String(url).includes("/services") && options.method === "POST")).toBe(true);
    expect(fetch.mock.calls.some(([url, options]) => String(url).includes("/services/service-1") && options.method === "PUT")).toBe(true);
    expect(fetch.mock.calls.some(([url, options]) => String(url).includes("/appointments/appointment-1") && options.method === "DELETE")).toBe(true);
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
