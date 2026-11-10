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
  return vi.spyOn(global, "fetch").mockImplementation(async (url) => {
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
      expect(screen.getByText(/Backend: online/i)).toBeInTheDocument();
    });
  });

  it("loads a business and its active services", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic/services", {
        data: {
          status: "success",
          services: [{ id: "service-1", service_name: "Haircut", duration_minutes: 30 }],
        },
      }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
            address: "Main Street",
          },
        },
      }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);

    expect(await screen.findByText("Demo Clinic")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Haircut \(30 min\)/i })).toBeInTheDocument();
  });

  it("shows an error when loading a business fails", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic", { status: 404, data: { message: "Business not found" } }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);

    expect(await screen.findByText("Business not found")).toBeInTheDocument();
  });

  it("books an appointment through the public booking endpoint", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic/services", {
        data: {
          status: "success",
          services: [{ id: "service-1", service_name: "Haircut", duration_minutes: 30 }],
        },
      }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
      ["/api/public/bookings", {
        data: {
          status: "success",
          message: "Appointment booked successfully",
          appointment_id: "appointment-1",
          appointment: {
            id: "appointment-1",
            status: "booked",
            scheduled_at: "2026-11-12T10:00:00.000Z",
          },
        },
      }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);
    await screen.findByText("Demo Clinic");

    await user.selectOptions(screen.getAllByRole("combobox")[0], "service-1");
    await user.type(screen.getByPlaceholderText(/enter your name/i), "John Doe");
    await user.type(screen.getByPlaceholderText(/enter phone number/i), "1234567890");
    await user.selectOptions(screen.getAllByRole("combobox")[1], "appointment");

    const dateTimeInput = document.querySelector('input[type="datetime-local"]');
    await user.type(dateTimeInput, "2026-11-12T10:00");

    await user.click(screen.getByRole("button", { name: /submit booking/i }));

    expect(await screen.findByText("Request Submitted")).toBeInTheDocument();
    expect(screen.getByText("Appointment ID: appointment-1")).toBeInTheDocument();
  });

  it("registers a walk-in and displays token details", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic/services", {
        data: {
          status: "success",
          services: [{ id: "service-1", service_name: "Haircut", duration_minutes: 30 }],
        },
      }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
      ["/api/public/walk-in", {
        data: {
          status: "success",
          message: "Walk-in registered successfully",
          queue_token: {
            id: "token-1",
            token_number: 7,
            tracking_code: "tracking-123",
            estimated_wait_minutes: 15,
            status: "waiting",
          },
        },
      }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);
    await screen.findByText("Demo Clinic");

    await user.selectOptions(screen.getAllByRole("combobox")[0], "service-1");
    await user.type(screen.getByPlaceholderText(/enter your name/i), "Jane Doe");
    await user.type(screen.getByPlaceholderText(/enter phone number/i), "0987654321");

    await user.click(screen.getByRole("button", { name: /submit booking/i }));

    expect(await screen.findByText("Request Submitted")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("tracking-123")).toBeInTheDocument();
  });

  it("tracks a token using the backend tracking response", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/track/tracking-123", {
        data: {
          status: "success",
          tracking: {
            token_number: 7,
            queue_status: "waiting",
            customers_ahead: 2,
            estimated_wait_minutes: 10,
          },
        },
      }],
    ]);

    render(<App />);

    await user.type(screen.getByPlaceholderText(/enter tracking code/i), "tracking-123");
    await user.click(screen.getByRole("button", { name: /track token/i }));

    expect(await screen.findByText(/Your Token/i)).toBeInTheDocument();
    expect(screen.getByText("#7")).toBeInTheDocument();
    expect(screen.getByText(/waiting/i)).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/10 min/i)).toBeInTheDocument();
  });

  it("shows an error for an invalid tracking code", async () => {
    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/track/bad-code", { status: 404, data: { message: "Tracking code not found" } }],
    ]);

    render(<App />);

    await user.type(screen.getByPlaceholderText(/enter tracking code/i), "bad-code");
    await user.click(screen.getByRole("button", { name: /track token/i }));

    expect(await screen.findByText("Tracking code not found")).toBeInTheDocument();
  });

  it("logs in an admin and loads the queue", async () => {
    localStorage.setItem("queueless_token", "admin-token");

    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic/services", { data: { status: "success", services: [] } }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
      ["/api/businesses/business-1/queue", {
        data: {
          status: "success",
          waiting: [
            {
              id: "token-1",
              token_number: 1,
              customer_name: "Alice",
              status: "waiting",
            },
          ],
          called: [],
          completed: [],
          skipped: [],
          cancelled: [],
        },
      }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /switch to admin/i })[0]);
    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);
    await screen.findByText("Selected: Demo Clinic");

    await user.click(screen.getByRole("button", { name: /refresh queue/i }));

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });

  it("calls the next customer and refreshes the queue", async () => {
    localStorage.setItem("queueless_token", "admin-token");

    mockFetch([
      ["/api/public/business/demo-clinic/services", { data: { status: "success", services: [] } }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
      ["/api/businesses/business-1/queue/call-next", { data: { status: "success", message: "Next customer called" } }],
      ["/api/businesses/business-1/queue", {
        data: {
          status: "success",
          waiting: [],
          called: [
            {
              id: "token-1",
              token_number: 1,
              customer_name: "Alice",
              status: "called",
            },
          ],
          completed: [],
          skipped: [],
          cancelled: [],
        },
      }],
      ["/api/health", { data: {} }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /switch to admin/i })[0]);
    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);
    await screen.findByText("Selected: Demo Clinic");

    await user.click(screen.getByRole("button", { name: /call next/i }));

    expect(await screen.findByText("Next customer called")).toBeInTheDocument();
  });

  it("completes, skips and cancels queue tokens", async () => {
    localStorage.setItem("queueless_token", "admin-token");

    mockFetch([
      ["/api/public/business/demo-clinic/services", { data: { status: "success", services: [] } }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
      ["/api/businesses/business-1/queue", {
        data: {
          status: "success",
          waiting: [
            {
              id: "token-1",
              token_number: 1,
              customer_name: "Alice",
              status: "waiting",
            },
          ],
          called: [],
          completed: [],
          skipped: [],
          cancelled: [],
        },
      }],
      ["/api/businesses/business-1/queue/token-1/complete", { data: { status: "success", message: "Customer completed" } }],
      ["/api/businesses/business-1/queue/token-1/skip", { data: { status: "success", message: "Customer skipped" } }],
      ["/api/businesses/business-1/queue/token-1/cancel", { data: { status: "success", message: "Customer cancelled" } }],
      ["/api/health", { data: {} }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /switch to admin/i })[0]);
    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);
    await screen.findByText("Selected: Demo Clinic");

    await user.click(screen.getByRole("button", { name: /refresh queue/i }));
    await screen.findByText("Alice");

    await user.click(screen.getByRole("button", { name: /complete/i }));
    expect(await screen.findByText("Token complete successful")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /skip/i }));
    expect(await screen.findByText("Token skip successful")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(await screen.findByText("Token cancel successful")).toBeInTheDocument();
  });

  it("pauses and resumes the queue and disables Call Next while paused", async () => {
    localStorage.setItem("queueless_token", "admin-token");

    mockFetch([
      ["/api/public/business/demo-clinic/services", { data: { status: "success", services: [] } }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
      ["/api/businesses/business-1/queue", {
        data: {
          status: "success",
          queue_paused: false,
          waiting: [],
          called: [],
          completed: [],
          skipped: [],
          cancelled: [],
        },
      }],
      ["/api/businesses/business-1/queue/pause", { data: { status: "success", message: "Queue paused" } }],
      ["/api/businesses/business-1/queue/resume", { data: { status: "success", message: "Queue resumed" } }],
      ["/api/health", { data: {} }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /switch to admin/i })[0]);
    await user.click(screen.getAllByRole("button", { name: /load business/i })[0]);
    await screen.findByText("Selected: Demo Clinic");

    await user.click(screen.getByRole("button", { name: /pause queue/i }));
    expect(await screen.findByText("Queue paused")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /call next/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /resume queue/i }));
    expect(await screen.findByText("Queue resumed")).toBeInTheDocument();
  });

  it("logs out and returns to the admin login view", async () => {
    localStorage.setItem("queueless_token", "admin-token");

    mockFetch([
      ["/api/health", { data: {} }],
      ["/api/public/business/demo-clinic/services", { data: { status: "success", services: [] } }],
      ["/api/public/business/demo-clinic", {
        data: {
          status: "success",
          business: {
            id: "business-1",
            business_name: "Demo Clinic",
            business_type: "Clinic",
          },
        },
      }],
    ]);

    render(<App />);

    await user.click(screen.getAllByRole("button", { name: /switch to admin/i })[0]);
    expect(await screen.findByText("Queue Management")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /logout/i }));

    expect(await screen.findByText("Welcome Back")).toBeInTheDocument();
    expect(localStorage.getItem("queueless_token")).toBeNull();
  });
});