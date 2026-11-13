/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:5000/api";

function authHeaders() {
  const token = localStorage.getItem("queueless_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, options = {}) {
  const customerToken = localStorage.getItem("queueless_customer_token");
  // merge customer token if present and no admin token
  if (customerToken && !localStorage.getItem("queueless_token")) {
    options.headers = { ...(options.headers || {}), Authorization: `Bearer ${customerToken}` };
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
      ...authHeaders(),
      ...(customerToken &&
      (path.startsWith("/customer-auth/") ||
        path.startsWith("/public/bookings") ||
        path.startsWith("/public/walk-in"))
        ? { Authorization: `Bearer ${customerToken}` }
        : {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || data.error || "Request failed");
  return data;
}

function Icon({ children }) {
  return <span className="nav-icon" aria-hidden="true">{children}</span>;
}

function StatCard({ label, value, detail, icon }) {
  return (
    <article className="stat-card">
      <div className="stat-card-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

export default function App() {
  const [role, setRole] = useState("customer");
  const [backendStatus, setBackendStatus] = useState("checking");
  const [notice, setNotice] = useState("");
  const [token, setToken] = useState(
    localStorage.getItem("queueless_token") || ""
  );
  const [customerToken, setCustomerToken] = useState(
    localStorage.getItem("queueless_customer_token") || ""
  );
  const [customerAppointments, setCustomerAppointments] = useState([]);
  const [customerTokens, setCustomerTokens] = useState([]);

  const [businessSlug, setBusinessSlug] = useState("demo-clinic");
  const [business, setBusiness] = useState(null);
  const [publicServices, setPublicServices] = useState([]);
  const [queue, setQueue] = useState([]);
  const [queuePaused, setQueuePaused] = useState(false);
  const [booking, setBooking] = useState(null);
  const [trackingCode, setTrackingCode] = useState("");
  const [trackedToken, setTrackedToken] = useState(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showRegister, setShowRegister] = useState(false);
  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirm, setRegConfirm] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerPassword, setCustomerPassword] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [selectedService, setSelectedService] = useState("");
  const [appointmentTime, setAppointmentTime] = useState("");
  const [mode, setMode] = useState("appointment");

  const [businesses, setBusinesses] = useState([]);
  const [selectedBusinessId, setSelectedBusinessId] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => {
        if (!r.ok) throw new Error("Backend unavailable");
        return r.json();
      })
      .then(() => setBackendStatus("online"))
      .catch(() => setBackendStatus("offline"));
  }, []);

  const notify = (message) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 3500);
  };

  const loadPublicBusiness = async () => {
    try {
      const biz = await api(`/public/business/${businessSlug}`);
      setBusiness(biz.business);
      setSelectedBusinessId(biz.business.id);

      const svc = await api(`/public/business/${businessSlug}/services`);
      setPublicServices(svc.services || []);

      notify("Business loaded successfully");
    } catch (err) {
      notify(err.message);
    }
  };

  const createBooking = async (e) => {
    e.preventDefault();

    try {
      const payload = {
        slug: businessSlug,
        service_id: selectedService,
        customer_name: customerName,
        customer_phone: customerPhone,
        customer_email: customerEmail,
      };

      let data;

      if (mode === "appointment") {
        payload.appointment_time = appointmentTime;

        data = await api("/public/bookings", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        setBooking({ ...data, type: "appointment" });
      } else {
        data = await api("/public/walk-in", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        setBooking({
          ...data,
          type: "walkin",
          token_number: data.queue_token?.token_number,
          tracking_code: data.queue_token?.tracking_code,
          estimated_wait_minutes:
            data.queue_token?.estimated_wait_minutes ??
            data.estimated_wait_minutes,
        });
      }

      notify("Your request has been submitted");
    } catch (err) {
      notify(err.message);
    }
  };

  const track = async (e) => {
    e.preventDefault();

    try {
      const data = await api(`/public/track/${trackingCode}`);
      setTrackedToken(data.tracking || data);
    } catch (err) {
      setTrackedToken({ error: err.message });
    }
  };

  const login = async (e) => {
    e.preventDefault();

    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });

      localStorage.setItem("queueless_token", data.access_token);
      setToken(data.access_token);
      notify("Login successful");
    } catch (err) {
      notify(err.message);
    }
  };

  const register = async (e) => {
    e.preventDefault();
    if (regPassword !== regConfirm) {
      notify("Passwords do not match");
      return;
    }
    try {
      const data = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({ full_name: regName, email: regEmail, password: regPassword }),
      });
      localStorage.setItem("queueless_token", data.access_token);
      setToken(data.access_token);
      notify("Registration successful");
      setShowRegister(false);
    } catch (err) {
      notify(err.message);
    }
  };

  const customerLogin = async (e) => {
    e.preventDefault();
    try {
      const data = await api("/customer-auth/login", { method: "POST", body: JSON.stringify({ email: customerEmail, password: customerPassword }) });
      localStorage.setItem("queueless_customer_token", data.access_token);
      setCustomerToken(data.access_token);
      notify("Customer login successful");
      try {
        const appointments = await api("/customer-auth/appointments");
        setCustomerAppointments(appointments.appointments || []);
        const queueTokens = await api("/customer-auth/queue-tokens");
        setCustomerTokens(queueTokens.tokens || []);
      } catch (err) {
        notify(err.message);
      }
    } catch (err) {
      notify(err.message);
    }
  };

  const customerRegister = async (e) => {
    e.preventDefault();
    try {
      const data = await api("/customer-auth/register", { method: "POST", body: JSON.stringify({ full_name: customerName, email: customerEmail, phone: customerPhone, password: customerPassword }) });
      localStorage.setItem("queueless_customer_token", data.access_token);
      setCustomerToken(data.access_token);
      notify("Customer registration successful");
    } catch (err) {
      notify(err.message);
    }
  };

  const logout = () => {
    localStorage.removeItem("queueless_token");
    setToken("");
    setBusinesses([]);
    setSelectedBusinessId("");
    setQueue([]);
    setRole("customer");
    notify("You have been logged out");
  };

  const loadBusinesses = async () => {
    try {
      const data = await api("/businesses");
      const list = data.businesses || [];

      setBusinesses(list);

      if (!selectedBusinessId && list.length) {
        setSelectedBusinessId(list[0].id);
      }
    } catch (err) {
      notify(err.message);
    }
  };

  const loadBusinessData = async (businessId) => {
    if (!businessId) return;

    try {
      const [svc, q] = await Promise.all([
        api(`/businesses/${businessId}/services`),
        api(`/businesses/${businessId}/queue`),
      ]);

      setPublicServices(svc.services || []);
      setQueue(q.queue || q.waiting || []);
      setQueuePaused(q.queue_paused || false);
    } catch (err) {
      notify(err.message);
    }
  };

  useEffect(() => {
    if (token) loadBusinesses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (selectedBusinessId && token) {
      loadBusinessData(selectedBusinessId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBusinessId, token]);

  const loadQueue = async () => {
    if (!selectedBusinessId) return;

    try {
      const data = await api(
        `/businesses/${selectedBusinessId}/queue`
      );

      setQueue(data.queue || data.waiting || []);
      setQueuePaused(data.queue_paused || false);
    } catch (err) {
      notify(err.message);
    }
  };

  const callNext = async () => {
    if (!selectedBusinessId) return;

    try {
      await api(
        `/businesses/${selectedBusinessId}/queue/call-next`,
        { method: "POST" }
      );

      await loadBusinessData(selectedBusinessId);
      notify("Next customer called");
    } catch (err) {
      notify(err.message);
    }
  };

  const queueAction = async (tokenId, action) => {
    if (!selectedBusinessId) return;

    try {
      await api(
        `/businesses/${selectedBusinessId}/queue/${tokenId}/${action}`,
        { method: "POST" }
      );

      await loadBusinessData(selectedBusinessId);
      notify(`Token ${action} successful`);
    } catch (err) {
      notify(err.message);
    }
  };

  const pauseQueue = async () => {
    if (!selectedBusinessId) return;

    try {
      await api(
        `/businesses/${selectedBusinessId}/queue/pause`,
        { method: "POST" }
      );

      setQueuePaused(true);
      notify("Queue paused");
    } catch (err) {
      notify(err.message);
    }
  };

  const resumeQueue = async () => {
    if (!selectedBusinessId) return;

    try {
      await api(
        `/businesses/${selectedBusinessId}/queue/resume`,
        { method: "POST" }
      );

      setQueuePaused(false);
      notify("Queue resumed");
    } catch (err) {
      notify(err.message);
    }
  };

  const selectedBusiness = businesses.find(
    (item) => String(item.id) === String(selectedBusinessId)
  );

  const waitingCount = useMemo(
    () =>
      queue.filter((item) =>
        ["waiting", "pending"].includes(
          String(item.status).toLowerCase()
        )
      ).length,
    [queue]
  );

  const servingCount = useMemo(
    () =>
      queue.filter((item) =>
        ["called", "serving", "in_progress"].includes(
          String(item.status).toLowerCase()
        )
      ).length,
    [queue]
  );

  return (
    <div
      className={`app-shell ${
        role === "admin" ? "admin-mode" : "customer-mode"
      }`}
    >
      <header className="topbar">
        <a
          className="brand"
          href="#home"
          onClick={(e) => e.preventDefault()}
        >
          <span className="brand-mark">Q</span>
          <span>
            Queue<span className="brand-light">Less</span>
          </span>
        </a>

        <div className="topbar-right">
          <span className={`connection-pill ${backendStatus}`}>
            <i />
            {backendStatus === "online"
              ? "System online"
              : backendStatus === "offline"
                ? "Backend offline"
                : "Checking system"}
          </span>

          <button
            className="btn btn-switch"
            onClick={() =>
              setRole(role === "customer" ? "admin" : "customer")
            }
          >
            {role === "customer"
              ? "Admin portal"
              : "Customer view"}
          </button>

          {token && (
            <button className="btn btn-logout" onClick={logout}>
              Logout
            </button>
          )}
        </div>
      </header>

      {notice && (
        <div className="toast" role="status">
          {notice}
        </div>
      )}

      {role === "customer" && (
        <main className="customer-page">
          <section className="customer-hero-layout">
            <div className="customer-hero-art">
              <div className="customer-hero-orbit" />
              <div className="customer-hero-copy">
                <span className="eyebrow">A BETTER WAY TO WAIT</span>
                <h1>
                  Your time matters.
                  <br />
                  <span>Skip the waiting room.</span>
                </h1>
                <p>
                  Check in for your appointment or join the queue in just a
                  few simple steps.
                </p>
                <div className="customer-trust">
                  <span className="trust-check">✓</span>
                  Simple check-in
                  <span className="trust-separator">•</span>
                  Live queue tracking
                </div>
                <div className="customer-hero-bars" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                </div>
              </div>
            </div>

            <div className="customer-account-panel">
              <span className="eyebrow purple-eyebrow">CUSTOMER ACCOUNT</span>
              <h2>Welcome</h2>
              <p className="customer-account-description">
                Sign in or create an account to keep track of your visits.
              </p>
              <section className="customer-account" aria-labelledby="customer-account-title">
                <h3 id="customer-account-title">Customer Account</h3>
              {!customerToken ? (
                <>
                  <input
                    className="input"
                    autoComplete="name"
                    placeholder="Full name"
                    aria-label="Full name"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                  />
                  <input
                    className="input"
                    type="email"
                    autoComplete="email"
                    placeholder="Email"
                    aria-label="Email"
                    value={customerEmail}
                    onChange={(e) => setCustomerEmail(e.target.value)}
                  />
                  <input
                    className="input"
                    type="password"
                    autoComplete="current-password"
                    placeholder="Password"
                    aria-label="Password"
                    value={customerPassword}
                    onChange={(e) => setCustomerPassword(e.target.value)}
                  />
                  <div className="customer-account-actions">
                    <button className="btn btn-account" type="button" onClick={customerRegister}>
                      Register
                    </button>
                    <button className="btn btn-account" type="button" onClick={customerLogin}>
                      Login
                    </button>
                  </div>
                </>
              ) : (
                <div className="customer-account-summary">
                  <p>You’re signed in. Your appointments and queue tokens are below.</p>
                  <button
                    className="btn btn-account"
                    type="button"
                    onClick={() => {
                      localStorage.removeItem("queueless_customer_token");
                      setCustomerToken("");
                      setCustomerAppointments([]);
                      setCustomerTokens([]);
                      notify("You have been logged out");
                    }}
                  >
                    Log out
                  </button>
                  <div className="customer-account-records">
                    <div>
                      <h3>My appointments</h3>
                      {customerAppointments.length ? customerAppointments.map((appointment) => (
                        <p key={appointment.id}>
                          {appointment.service_name || "Appointment"} · {appointment.status} ·{" "}
                          {appointment.scheduled_at}
                        </p>
                      )) : <p>No appointments yet.</p>}
                    </div>
                    <div>
                      <h3>My queue tokens</h3>
                      {customerTokens.length ? customerTokens.map((queueToken) => (
                        <p key={queueToken.id}>
                          Token #{queueToken.token_number} · {queueToken.status} ·{" "}
                          {queueToken.ahead} ahead
                        </p>
                      )) : <p>No queue tokens yet.</p>}
                    </div>
                  </div>
                </div>
              )}
              </section>
            </div>
          </section>

          <section className="checkin-layout">
            <div className="checkin-aside">
              <span className="eyebrow purple-eyebrow">
                QUICK & EASY
              </span>
              <h2>Check in without the wait.</h2>
              <p>
                Select your service, enter your details and
                secure your place in line.
              </p>

              <div className="step-list">
                <div className="step-item">
                  <span>01</span>
                  <div>
                    <strong>Choose your service</strong>
                    <small>Select the service you need.</small>
                  </div>
                </div>

                <div className="step-item">
                  <span>02</span>
                  <div>
                    <strong>Enter your details</strong>
                    <small>Tell us how to identify you.</small>
                  </div>
                </div>

                <div className="step-item">
                  <span>03</span>
                  <div>
                    <strong>Get your token</strong>
                    <small>Track your place in the queue.</small>
                  </div>
                </div>
              </div>
            </div>

            <div className="checkin-card">
              <div className="checkin-card-heading">
                <div>
                  <span className="eyebrow">CUSTOMER CHECK-IN</span>
                  <h2>Book your visit</h2>
                  <p>Fill in the details below to get started.</p>
                </div>
                <span className="checkin-icon">✦</span>
              </div>

              <div className="business-loader">
                <label htmlFor="businessSlug">
                  Business code
                </label>
                <div className="business-loader-row">
                  <input
                    id="businessSlug"
                    className="input"
                    value={businessSlug}
                    onChange={(e) => setBusinessSlug(e.target.value)}
                    placeholder="Enter business code"
                  />
                  <button
                    className="btn btn-purple"
                    type="button"
                    onClick={loadPublicBusiness}
                  >
                    Load
                  </button>
                </div>

                {business && (
                  <div className="loaded-business">
                    <span className="business-check">✓</span>
                    <div>
                      <strong>{business.business_name}</strong>
                      <small>
                        {business.business_type || "Business loaded"}
                      </small>
                    </div>
                  </div>
                )}
              </div>

              <form className="checkin-form" onSubmit={createBooking}>
                <div className="field">
                  <label htmlFor="service">Select service</label>
                  <select
                    id="service"
                    className="input"
                    value={selectedService}
                    onChange={(e) => setSelectedService(e.target.value)}
                    required
                  >
                    <option value="">Choose a service</option>
                    {publicServices.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.service_name} ({s.duration_minutes} min)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="customerName">Full name</label>
                  <input
                    id="customerName"
                    className="input"
                    placeholder="Enter your full name"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    required
                  />
                </div>

                <div className="field-row">
                  <div className="field">
                    <label htmlFor="customerPhone">Phone number</label>
                    <input
                      id="customerPhone"
                      className="input"
                      placeholder="Phone number"
                      value={customerPhone}
                      onChange={(e) => setCustomerPhone(e.target.value)}
                      required
                    />
                  </div>

                  <div className="field">
                    <label htmlFor="customerEmail">Email address</label>
                    <input
                      id="customerEmail"
                      className="input"
                      type="email"
                      placeholder="Email (optional)"
                      value={customerEmail}
                      onChange={(e) => setCustomerEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="field">
                  <label htmlFor="mode">Check-in type</label>
                  <select
                    id="mode"
                    className="input"
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="appointment">Appointment</option>
                    <option value="walkin">Walk-in queue</option>
                  </select>
                </div>

                {mode === "appointment" && (
                  <div className="field">
                    <label htmlFor="appointmentTime">
                      Appointment date and time
                    </label>
                    <input
                      id="appointmentTime"
                      className="input"
                      type="datetime-local"
                      value={appointmentTime}
                      onChange={(e) =>
                        setAppointmentTime(e.target.value)
                      }
                      required
                    />
                  </div>
                )}

                <button
                  className="btn btn-purple submit-checkin"
                  type="submit"
                >
                  Continue to check-in <span>→</span>
                </button>

                <p className="privacy-note">
                  Your information is used only to manage your check-in.
                </p>
              </form>

              {booking && (
                <div className="booking-result">
                  <div className="result-icon">✓</div>
                  <div>
                    <strong>Request submitted successfully</strong>

                    {booking.type === "appointment" && (
                      <p>
                        Appointment ID: {booking.appointment?.id}
                      </p>
                    )}

                    {booking.type === "walkin" && (
                      <>
                        <p>
                          Token number: <b>#{booking.token_number}</b>
                        </p>
                        <p>
                          Tracking code: <b>{booking.tracking_code}</b>
                        </p>
                      </>
                    )}

                    <p>
                      Estimated wait:{" "}
                      {booking.estimated_wait_minutes ?? "To be confirmed"}{" "}
                      minutes
                    </p>
                  </div>
                </div>
              )}
            </div>
          </section>

          <section className="track-section">
            <div>
              <span className="eyebrow purple-eyebrow">
                ALREADY CHECKED IN?
              </span>
              <h2>Track your place in line</h2>
              <p>
                Enter the tracking code you received after joining
                the queue.
              </p>
            </div>

            <form className="track-form" onSubmit={track}>
              <input
                className="input"
                placeholder="Enter tracking code"
                value={trackingCode}
                onChange={(e) => setTrackingCode(e.target.value)}
                required
              />
              <button className="btn btn-purple" type="submit">
                Track token
              </button>
            </form>

            {trackedToken &&
              (trackedToken.error ? (
                <p className="track-error">{trackedToken.error}</p>
              ) : (
                <div className="tracking-result">
                  <div>
                    <small>YOUR TOKEN</small>
                    <strong>#{trackedToken.token_number}</strong>
                  </div>
                  <div>
                    <small>STATUS</small>
                    <strong>{trackedToken.queue_status}</strong>
                  </div>
                  <div>
                    <small>CUSTOMERS AHEAD</small>
                    <strong>{trackedToken.customers_ahead}</strong>
                  </div>
                  <div>
                    <small>ESTIMATED WAIT</small>
                    <strong>
                      {trackedToken.estimated_wait_minutes} min
                    </strong>
                  </div>
                </div>
              ))}
          </section>
        </main>
      )}

      {role === "admin" && !token && (
        <main className="login-page">
          <div className="login-art">
            <div className="login-art-orbit" />
            <div className="login-art-card">
              <span>Q</span>
              <strong>QueueLess</strong>
              <p>
                Manage your queue.
                <br />
                Make every visit smoother.
              </p>
              <div className="mini-bars">
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>

          <form className="login-card" onSubmit={login}>
            <span className="eyebrow">ADMINISTRATOR ACCESS</span>
            <h1>Welcome back</h1>
            <p>Sign in to manage your business queue.</p>

            <label htmlFor="email">Email address</label>
            <input
              id="email"
              className="input"
              type="email"
              placeholder="admin@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <label htmlFor="password">Password</label>
            <div style={{ position: "relative" }}>
              <input
                id="password"
                className="input"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                style={{ position: "absolute", right: "10px", top: "10px", border: "none", background: "transparent", cursor: "pointer" }}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>

            <button className="btn btn-admin-login" type="submit">
              Sign in to dashboard <span>→</span>
            </button>

            <div style={{ marginTop: "12px" }}>
              <button type="button" className="btn btn-secondary" onClick={() => setShowRegister((v) => !v)}>
                {showRegister ? "Back to login" : "Create account"}
              </button>
            </div>

            {showRegister && (
              <form onSubmit={register} style={{ marginTop: "16px" }}>
                <input className="input" placeholder="Full name" value={regName} onChange={(e) => setRegName(e.target.value)} required />
                <input className="input" type="email" placeholder="Email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} required />
                <input className="input" type="password" placeholder="Password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} required />
                <input className="input" type="password" placeholder="Confirm password" value={regConfirm} onChange={(e) => setRegConfirm(e.target.value)} required />
                <button className="btn" type="submit">Register</button>
              </form>
            )}

            <div style={{ marginTop: "12px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <button type="button" className="btn btn-secondary" onClick={async () => {
                const email = prompt("Enter your registered email:");
                if (!email) return;
                try {
                  const data = await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
                  if (data.reset_token) {
                    const newPassword = prompt("Dev reset token received. Enter new password:");
                    if (newPassword) {
                      await api("/auth/reset-password", { method: "POST", body: JSON.stringify({ token: data.reset_token, password: newPassword }) });
                      alert("Password reset successful.");
                    }
                  } else {
                    alert("If the email exists, a reset link has been sent.");
                  }
                } catch (err) {
                  alert(err.message);
                }
              }}>
                Forgot password
              </button>
            </div>

            <small className="login-footnote">
              Secure access for QueueLess business administrators.
            </small>
          </form>
        </main>
      )}

      {role === "admin" && token && (
        <div className="admin-layout">
          <aside className="admin-sidebar">
            <a
              className="admin-brand"
              href="#dashboard"
              onClick={(e) => e.preventDefault()}
            >
              <span className="brand-mark">Q</span>
              <span>
                Queue<span>Less</span>
              </span>
            </a>

            <div className="sidebar-caption">WORKSPACE</div>

            <nav className="sidebar-nav">
              <a className="active" href="#overview">
                <Icon>▦</Icon>Dashboard
              </a>
              <a href="#queue">
                <Icon>☷</Icon>Queues
              </a>
              <a href="#queue">
                <Icon>▣</Icon>Appointments
              </a>
              <a href="#services">
                <Icon>◈</Icon>Services
              </a>
            </nav>

            <div className="sidebar-bottom">
              <div className="sidebar-status">
                <i />
                API connection <strong>{backendStatus}</strong>
              </div>

              <button onClick={logout}>
                <Icon>↪</Icon>Logout
              </button>
            </div>
          </aside>

          <main className="admin-main" id="overview">
            <div className="admin-topbar">
              <div>
                <span className="admin-greeting">
                  WORKSPACE OVERVIEW
                </span>
                <h1>Dashboard</h1>
                <p>
                  Monitor your queue and manage customer flow.
                </p>
              </div>

              <div className="admin-top-actions">
                <span className={`connection-pill ${backendStatus}`}>
                  <i /> {backendStatus}
                </span>
                <div className="admin-avatar">A</div>
              </div>
            </div>

            <section className="admin-toolbar">
              <div className="business-select">
                <label htmlFor="businessSelect">Current business</label>
                <select
                  id="businessSelect"
                  className="input"
                  value={selectedBusinessId}
                  onChange={(e) =>
                    setSelectedBusinessId(e.target.value)
                  }
                >
                  <option value="">Select business</option>
                  {businesses.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.business_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="toolbar-actions">
                <button className="btn btn-outline" onClick={loadQueue}>
                  ↻ Refresh
                </button>
                <button
                  className="btn btn-teal"
                  onClick={callNext}
                  disabled={!selectedBusinessId || queuePaused}
                >
                  Call next customer →
                </button>
              </div>
            </section>

            <section className="stats-grid">
              <StatCard
                label="Total queue entries"
                value={queue.length}
                detail="Currently loaded queue"
                icon="▤"
              />
              <StatCard
                label="Waiting customers"
                value={waitingCount}
                detail="Customers waiting to be served"
                icon="◷"
              />
              <StatCard
                label="Currently serving"
                value={servingCount}
                detail="Called or in service"
                icon="◉"
              />
              <StatCard
                label="Queue status"
                value={queuePaused ? "Paused" : "Active"}
                detail={
                  queuePaused
                    ? "New calls are paused"
                    : "Queue is accepting calls"
                }
                icon="⌁"
              />
            </section>

            <section className="admin-content-grid">
              <div className="dashboard-panel queue-panel" id="queue">
                <div className="panel-heading">
                  <div>
                    <h2>Live waiting list</h2>
                    <p>
                      {selectedBusiness?.business_name ||
                        "Select a business to view its queue"}
                    </p>
                  </div>

                  <span
                    className={`queue-state ${
                      queuePaused ? "paused" : "active"
                    }`}
                  >
                    <i />
                    {queuePaused ? "Paused" : "Live queue"}
                  </span>
                </div>

                <div className="queue-controls">
                  <button
                    className="btn btn-teal"
                    onClick={callNext}
                    disabled={!selectedBusinessId || queuePaused}
                  >
                    Call next
                  </button>

                  <button
                    className="btn btn-outline"
                    onClick={pauseQueue}
                    disabled={!selectedBusinessId || queuePaused}
                  >
                    Pause queue
                  </button>

                  <button
                    className="btn btn-outline"
                    onClick={resumeQueue}
                    disabled={!selectedBusinessId || !queuePaused}
                  >
                    Resume queue
                  </button>
                </div>

                <div className="table-wrap">
                  <table className="queue-table">
                    <thead>
                      <tr>
                        <th>TOKEN ID</th>
                        <th>CUSTOMER</th>
                        <th>STATUS</th>
                        <th>ACTIONS</th>
                      </tr>
                    </thead>

                    <tbody>
                      {queue.length ? (
                        queue.map((q) => (
                          <tr key={q.id}>
                            <td>
                              <strong>#{q.token_number}</strong>
                            </td>
                            <td>{q.customer_name || "Customer"}</td>
                            <td>
                              <span
                                className={`status-badge status-${String(
                                  q.status || "waiting"
                                ).toLowerCase()}`}
                              >
                                {q.status || "Waiting"}
                              </span>
                            </td>
                            <td>
                              <div className="row-actions">
                                <button
                                  onClick={() =>
                                    queueAction(q.id, "complete")
                                  }
                                >
                                  Complete
                                </button>
                                <button
                                  onClick={() =>
                                    queueAction(q.id, "skip")
                                  }
                                >
                                  Skip
                                </button>
                                <button
                                  className="danger-action"
                                  onClick={() =>
                                    queueAction(q.id, "cancel")
                                  }
                                >
                                  Cancel
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="4" className="empty-queue">
                            {selectedBusinessId
                              ? "No queue entries to display."
                              : "Choose a business to load its queue."}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <aside className="dashboard-side">
                <div className="dashboard-panel queue-health">
                  <div className="panel-heading">
                    <div>
                      <h2>Queue controls</h2>
                      <p>Manage customer flow</p>
                    </div>
                    <span className="panel-icon">⌁</span>
                  </div>

                  <div className="health-status">
                    <span
                      className={`health-indicator ${
                        queuePaused ? "is-paused" : ""
                      }`}
                    />
                    <div>
                      <strong>
                        {queuePaused
                          ? "Queue is paused"
                          : "Queue is running"}
                      </strong>
                      <small>
                        {queuePaused
                          ? "Resume when you're ready to serve."
                          : "Your queue is ready for the next customer."}
                      </small>
                    </div>
                  </div>

                  <div className="side-control-buttons">
                    <button
                      className="btn btn-teal"
                      onClick={callNext}
                      disabled={!selectedBusinessId || queuePaused}
                    >
                      Call next customer
                    </button>

                    <button
                      className="btn btn-outline"
                      onClick={queuePaused ? resumeQueue : pauseQueue}
                      disabled={!selectedBusinessId}
                    >
                      {queuePaused ? "Resume queue" : "Pause queue"}
                    </button>
                  </div>
                </div>

                <div
                  className="dashboard-panel service-panel"
                  id="services"
                >
                  <div className="panel-heading">
                    <div>
                      <h2>Available services</h2>
                      <p>Services configured for this business</p>
                    </div>
                    <span className="panel-icon">◈</span>
                  </div>

                  {publicServices.length ? (
                    <ul className="service-list">
                      {publicServices.map((s) => (
                        <li key={s.id}>
                          <span className="service-dot" />
                          <span>{s.service_name}</span>
                          <small>{s.duration_minutes} min</small>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted-empty">
                      No service information loaded yet.
                    </p>
                  )}
                </div>
              </aside>
            </section>

            <footer className="admin-footer">
              QueueLess <span>•</span> Queue management workspace
            </footer>
          </main>
        </div>
      )}
    </div>
  );
}