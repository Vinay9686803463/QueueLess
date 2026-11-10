import { useEffect, useState } from "react";
import "./App.css";

// Local development API URL.
// Change this to your deployed backend URL when deploying the frontend.
const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000/api";

function authHeaders() {
  const token = localStorage.getItem("queueless_token");

  return token
    ? { Authorization: `Bearer ${token}` }
    : {};
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
      ...authHeaders(),
    },
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.message || data.error || `Request failed (${response.status})`
    );
  }

  return data;
}

export default function App() {
  const [role, setRole] = useState("customer");

  const [backendStatus, setBackendStatus] = useState("checking");
  const [notice, setNotice] = useState("");

  const [token, setToken] = useState(
    localStorage.getItem("queueless_token") || ""
  );

  const [businessSlug, setBusinessSlug] = useState("demo-clinic");
  const [business, setBusiness] = useState(null);

  const [services, setServices] = useState([]);
  const [queue, setQueue] = useState([]);

  const [booking, setBooking] = useState(null);

  const [trackingCode, setTrackingCode] = useState("");
  const [trackedToken, setTrackedToken] = useState(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");

  const [selectedService, setSelectedService] = useState("");
  const [appointmentTime, setAppointmentTime] = useState("");

  const [mode, setMode] = useState("walk-in");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api("/health")
      .then(() => setBackendStatus("online"))
      .catch(() => setBackendStatus("offline"));
  }, []);

  const notify = (message) => {
    setNotice(message);

    window.setTimeout(() => {
      setNotice("");
    }, 3500);
  };

  // Load business and its services.
  // These public endpoints must exist in your backend.
  const loadBusiness = async () => {
    if (!businessSlug.trim()) {
      notify("Enter a business slug");
      return;
    }

    setLoading(true);

    try {
      const businessData = await api(
        `/public/business/${encodeURIComponent(businessSlug.trim())}`
      );

      const loadedBusiness = businessData.business;

      if (!loadedBusiness?.id) {
        throw new Error("Business information was not returned");
      }

      setBusiness(loadedBusiness);

      const serviceData = await api(
        `/public/business/${encodeURIComponent(businessSlug.trim())}/services`
      );

      setServices(serviceData.services || []);
      setSelectedService("");

      setBooking(null);
      setQueue([]);

      notify("Business loaded successfully");
    } catch (error) {
      setBusiness(null);
      setServices([]);
      notify(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Load queue for the logged-in business owner.
  const loadQueue = async () => {
    if (!business?.id) {
      notify("Load your business first");
      return;
    }

    try {
      const data = await api(`/businesses/${business.id}/queue`);

      setQueue(data.queue || []);
    } catch (error) {
      notify(error.message);
    }
  };

  // Admin login.
  const login = async (event) => {
    event.preventDefault();

    if (!email.trim() || !password) {
      notify("Enter email and password");
      return;
    }

    setLoading(true);

    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          password,
        }),
      });

      if (!data.access_token) {
        throw new Error("Login response did not contain an access token");
      }

      localStorage.setItem("queueless_token", data.access_token);

      setToken(data.access_token);
      setPassword("");

      notify("Login successful");
    } catch (error) {
      notify(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Create appointment or walk-in.
  const createBooking = async (event) => {
    event.preventDefault();

    if (!business?.id) {
      notify("Load a business first");
      return;
    }

    if (!selectedService) {
      notify("Select a service");
      return;
    }

    if (!customerName.trim() || !customerPhone.trim()) {
      notify("Enter your name and phone number");
      return;
    }

    if (mode === "appointment" && !appointmentTime) {
      notify("Select an appointment date and time");
      return;
    }

    setLoading(true);

    try {
      let data;

      if (mode === "walk-in") {
        // Existing backend public walk-in endpoint.
        data = await api("/public/walk-in", {
          method: "POST",
          body: JSON.stringify({
            business_id: business.id,
            service_id: selectedService,
            customer_name: customerName.trim(),
            customer_phone: customerPhone.trim(),
            customer_email: customerEmail.trim() || null,
          }),
        });
      } else {
        // Existing appointment endpoint requires JWT authentication.
        // This request is not public customer booking.
        data = await api("/appointments", {
          method: "POST",
          body: JSON.stringify({
            business_id: business.id,
            service_id: selectedService,
            customer_name: customerName.trim(),
            customer_phone: customerPhone.trim(),
            customer_email: customerEmail.trim() || null,
            scheduled_at: new Date(appointmentTime).toISOString(),
          }),
        });
      }

      setBooking(data);

      if (data.tracking_code) {
        setTrackingCode(data.tracking_code);
      }

      notify("Request submitted successfully");
    } catch (error) {
      notify(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Track customer token.
  const track = async (event) => {
    event.preventDefault();

    if (!trackingCode.trim()) {
      notify("Enter your tracking code");
      return;
    }

    try {
      const data = await api(
        `/public/track/${encodeURIComponent(trackingCode.trim())}`
      );

      setTrackedToken(data.tracking || data);
    } catch (error) {
      setTrackedToken({
        error: error.message,
      });
    }
  };

  // Call next waiting customer.
  const callNext = async () => {
    if (!business?.id) {
      notify("Load your business first");
      return;
    }

    try {
      await api(`/businesses/${business.id}/queue/call-next`, {
        method: "POST",
      });

      await loadQueue();

      notify("Next customer called");
    } catch (error) {
      notify(error.message);
    }
  };

  // Complete, skip or cancel a queue token.
  const queueAction = async (tokenId, action) => {
    if (!business?.id) {
      notify("Load your business first");
      return;
    }

    try {
      await api(
        `/businesses/${business.id}/queue/${tokenId}/${action}`,
        {
          method: "POST",
        }
      );

      await loadQueue();

      notify(`Token ${action} successful`);
    } catch (error) {
      notify(error.message);
    }
  };

  // Pause queue.
  const pauseQueue = async () => {
    if (!business?.id) {
      notify("Load your business first");
      return;
    }

    try {
      await api(`/businesses/${business.id}/queue/pause`, {
        method: "POST",
      });

      notify("Queue paused");
    } catch (error) {
      notify(error.message);
    }
  };

  // Resume queue.
  const resumeQueue = async () => {
    if (!business?.id) {
      notify("Load your business first");
      return;
    }

    try {
      await api(`/businesses/${business.id}/queue/resume`, {
        method: "POST",
      });

      notify("Queue resumed");
    } catch (error) {
      notify(error.message);
    }
  };

  const toggleRole = () => {
    const nextRole = role === "customer" ? "admin" : "customer";

    setRole(nextRole);
    setNotice("");
  };

  // Logout.
  const logout = () => {
    localStorage.removeItem("queueless_token");

    setToken("");
    setBusiness(null);
    setServices([]);
    setQueue([]);
    setMode("walk-in");

    setRole("customer");

    notify("Logged out successfully");
  };

  return (
    <div className="app-shell">
      {/* Navigation */}
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon">Q</span>
          <span>QueueLess</span>
        </div>

        <div className="topbar-actions">
          <button
            className="btn btn-secondary"
            onClick={toggleRole}
          >
            Switch to {role === "customer" ? "Admin" : "Customer"}
          </button>

          {token && (
            <button className="btn btn-logout" onClick={logout}>
              Logout
            </button>
          )}
        </div>
      </header>

      <main className="section">
        {/* Notification */}
        {notice && (
          <div className="notice success">
            {notice}
          </div>
        )}

        {/* Hero */}
        <section className="hero">
          <div className="hero-content">
            <span className="eyebrow">SMART QUEUE MANAGEMENT</span>

            <h1>
              Skip the wait.
              <br />
              <span>Save your time.</span>
            </h1>

            <p>
              Book appointments, join queues, and track your position
              without waiting in long lines.
            </p>

            <div className="backend-status">
              <span
                className={`status-dot ${backendStatus}`}
              />

              Backend: {backendStatus}
            </div>
          </div>

          <div className="hero-illustration">
            <div className="illustration-card">
              <div className="illustration-top">
                <span>YOUR QUEUE</span>
                <span className="live-label">LIVE</span>
              </div>

              <div className="illustration-number">05</div>
              <p>Customers ahead of you</p>

              <div className="progress-track">
                <div className="progress-fill" />
              </div>

              <div className="illustration-bottom">
                <span>Estimated waiting time</span>
                <strong>15 min</strong>
              </div>
            </div>
          </div>
        </section>

        {/* Customer section */}
        {role === "customer" && (
          <section className="content-section">
            <div className="section-heading">
              <span className="eyebrow">CUSTOMER PORTAL</span>
              <h2>Manage your visit</h2>
              <p>Load a business, book a service or track your queue.</p>
            </div>

            {/* Business */}
            <div className="card">
              <div className="card-heading">
                <div>
                  <h2>Find a Business</h2>
                  <p>Enter the business slug to continue.</p>
                </div>

                <span className="card-icon">01</span>
              </div>

              <div className="form-row">
                <input
                  className="input"
                  value={businessSlug}
                  onChange={(event) =>
                    setBusinessSlug(event.target.value)
                  }
                  placeholder="Business slug"
                />

                <button
                  className="btn"
                  onClick={loadBusiness}
                  disabled={loading}
                >
                  {loading ? "Loading..." : "Load Business"}
                </button>
              </div>
            </div>

            {/* Business information */}
            {business && (
              <div className="card business-card">
                <div>
                  <span className="eyebrow">SELECTED BUSINESS</span>
                  <h2>
                    {business.business_name || business.name}
                  </h2>

                  <p>
                    {business.business_type || "Business"}
                    {business.address ? ` • ${business.address}` : ""}
                  </p>
                </div>

                <span className="badge">Available</span>
              </div>
            )}

            {/* Booking */}
            <div className="card">
              <div className="card-heading">
                <div>
                  <h2>Book a Queue</h2>
                  <p>Enter your details to join the queue.</p>
                </div>

                <span className="card-icon">02</span>
              </div>

              <form onSubmit={createBooking}>
                <label>Choose Service</label>

                <select
                  className="input"
                  value={selectedService}
                  onChange={(event) =>
                    setSelectedService(event.target.value)
                  }
                  required
                >
                  <option value="">Select service</option>

                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.service_name || service.name}
                      {" "}
                      ({service.duration_minutes || service.duration} min)
                    </option>
                  ))}
                </select>

                <div className="grid grid-2">
                  <div>
                    <label>Full Name</label>
                    <input
                      className="input"
                      placeholder="Enter your name"
                      value={customerName}
                      onChange={(event) =>
                        setCustomerName(event.target.value)
                      }
                      required
                    />
                  </div>

                  <div>
                    <label>Phone Number</label>
                    <input
                      className="input"
                      type="tel"
                      placeholder="Enter phone number"
                      value={customerPhone}
                      onChange={(event) =>
                        setCustomerPhone(event.target.value)
                      }
                      required
                    />
                  </div>
                </div>

                <label>Email Address (Optional)</label>

                <input
                  className="input"
                  type="email"
                  placeholder="Enter email address"
                  value={customerEmail}
                  onChange={(event) =>
                    setCustomerEmail(event.target.value)
                  }
                />

                <label>Booking Type</label>

                <select
                  className="input"
                  value={mode}
                  onChange={(event) => setMode(event.target.value)}
                >
                  <option value="walk-in">Walk-in</option>
                  {token && (
                    <option value="appointment">Appointment</option>
                  )}
                </select>

                {mode === "appointment" && (
                  <>
                    <label>Appointment Date and Time</label>

                    <input
                      className="input"
                      type="datetime-local"
                      value={appointmentTime}
                      onChange={(event) =>
                        setAppointmentTime(event.target.value)
                      }
                      required
                    />
                  </>
                )}

                <button
                  className="btn btn-full"
                  type="submit"
                  disabled={loading}
                >
                  {loading ? "Submitting..." : "Submit Booking"}
                </button>
              </form>

              {/* Booking result */}
              {booking && (
                <div className="booking-result">
                  <div className="result-icon">✓</div>

                  <h3>Request Submitted</h3>

                  <p>
                    Your request has been processed by the server.
                  </p>

                  {booking.token_number != null && (
                    <div className="token-number">
                      {booking.token_number}
                    </div>
                  )}

                  {booking.tracking_code && (
                    <p>
                      <strong>Tracking Code:</strong>{" "}
                      {booking.tracking_code}
                    </p>
                  )}

                  {booking.estimated_wait_minutes != null && (
                    <p>
                      <strong>Estimated Wait:</strong>{" "}
                      {booking.estimated_wait_minutes} minutes
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Tracking */}
            <div className="card">
              <div className="card-heading">
                <div>
                  <h2>Track Your Token</h2>
                  <p>Check your current queue position.</p>
                </div>

                <span className="card-icon">03</span>
              </div>

              <form onSubmit={track}>
                <label>Tracking Code</label>

                <div className="form-row">
                  <input
                    className="input"
                    placeholder="Enter tracking code"
                    value={trackingCode}
                    onChange={(event) =>
                      setTrackingCode(event.target.value)
                    }
                    required
                  />

                  <button className="btn" type="submit">
                    Track Token
                  </button>
                </div>
              </form>

              {trackedToken && !trackedToken.error && (
                <div className="tracking-result">
                  <div className="tracking-header">
                    <div>
                      <span className="eyebrow">YOUR TOKEN</span>
                      <h2>#{trackedToken.token_number ?? "—"}</h2>
                    </div>

                    <span className="badge">
                      {trackedToken.status || "Unknown"}
                    </span>
                  </div>

                  <div className="grid grid-2 tracking-stats">
                    <div className="stat-box">
                      <span>Customers Ahead</span>
                      <strong>
                        {trackedToken.customers_ahead ?? "—"}
                      </strong>
                    </div>

                    <div className="stat-box">
                      <span>Estimated Wait</span>
                      <strong>
                        {trackedToken.estimated_wait_minutes != null
                          ? `${trackedToken.estimated_wait_minutes} min`
                          : "—"}
                      </strong>
                    </div>
                  </div>
                </div>
              )}

              {trackedToken?.error && (
                <p className="error-message">
                  {trackedToken.error}
                </p>
              )}
            </div>
          </section>
        )}

        {/* Admin section */}
        {role === "admin" && (
          <section className="content-section">
            {!token ? (
              <div className="login-wrapper">
                <div className="card login-card">
                  <div className="login-icon">Q</div>

                  <span className="eyebrow">ADMIN PORTAL</span>

                  <h2>Welcome Back</h2>

                  <p>Login to manage your business queue.</p>

                  <form onSubmit={login}>
                    <label>Email Address</label>

                    <input
                      className="input"
                      type="email"
                      placeholder="Enter email"
                      value={email}
                      onChange={(event) =>
                        setEmail(event.target.value)
                      }
                      required
                    />

                    <label>Password</label>

                    <input
                      className="input"
                      type="password"
                      placeholder="Enter password"
                      value={password}
                      onChange={(event) =>
                        setPassword(event.target.value)
                      }
                      required
                    />

                    <button
                      className="btn btn-full"
                      type="submit"
                      disabled={loading}
                    >
                      {loading ? "Logging in..." : "Login"}
                    </button>
                  </form>
                </div>
              </div>
            ) : (
              <>
                <div className="section-heading">
                  <span className="eyebrow">BUSINESS DASHBOARD</span>
                  <h2>Queue Management</h2>
                  <p>Manage customers and control your live queue.</p>
                </div>

                {/* Business controls */}
                <div className="card">
                  <h2>Business Settings</h2>

                  <label>Business Slug</label>

                  <div className="form-row">
                    <input
                      className="input"
                      value={businessSlug}
                      onChange={(event) =>
                        setBusinessSlug(event.target.value)
                      }
                      placeholder="Business slug"
                    />

                    <button
                      className="btn"
                      onClick={loadBusiness}
                      disabled={loading}
                    >
                      Load Business
                    </button>
                  </div>

                  {business && (
                    <p className="business-loaded">
                      Selected:{" "}
                      <strong>
                        {business.business_name || business.name}
                      </strong>
                    </p>
                  )}

                  <div className="action-toolbar">
                    <button className="btn" onClick={loadQueue}>
                      Refresh Queue
                    </button>

                    <button className="btn btn-success" onClick={callNext}>
                      Call Next
                    </button>

                    <button
                      className="btn btn-warning"
                      onClick={pauseQueue}
                    >
                      Pause Queue
                    </button>

                    <button
                      className="btn btn-secondary"
                      onClick={resumeQueue}
                    >
                      Resume Queue
                    </button>
                  </div>
                </div>

                {/* Queue table */}
                <div className="card">
                  <div className="card-heading">
                    <div>
                      <h2>Live Queue</h2>
                      <p>
                        {queue.length} queue entries currently loaded.
                      </p>
                    </div>

                    <span className="badge">Live Dashboard</span>
                  </div>

                  <div className="table-wrapper">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Token</th>
                          <th>Customer</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>

                      <tbody>
                        {queue.length === 0 ? (
                          <tr>
                            <td colSpan="4" className="empty-state">
                              No queue entries found. Refresh the queue.
                            </td>
                          </tr>
                        ) : (
                          queue.map((item) => (
                            <tr key={item.id}>
                              <td>
                                <strong>#{item.token_number}</strong>
                              </td>

                              <td>{item.customer_name || "Customer"}</td>

                              <td>
                                <span className={`status-badge status-${item.status}`}>
                                  {item.status}
                                </span>
                              </td>

                              <td>
                                <div className="table-actions">
                                  {["waiting", "called", "serving"].includes(
                                    item.status
                                  ) && (
                                    <>
                                      {["called", "serving"].includes(
                                        item.status
                                      ) && (
                                        <button
                                          className="btn btn-small btn-success"
                                          onClick={() =>
                                            queueAction(item.id, "complete")
                                          }
                                        >
                                          Complete
                                        </button>
                                      )}

                                      <button
                                        className="btn btn-small btn-warning"
                                        onClick={() =>
                                          queueAction(item.id, "skip")
                                        }
                                      >
                                        Skip
                                      </button>

                                      <button
                                        className="btn btn-small btn-danger"
                                        onClick={() =>
                                          queueAction(item.id, "cancel")
                                        }
                                      >
                                        Cancel
                                      </button>
                                    </>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </section>
        )}
      </main>

      <footer className="footer">
        <strong>QueueLess</strong>
        <p>Smart Appointment & Live Queue Management System</p>
      </footer>
    </div>
  );
}
