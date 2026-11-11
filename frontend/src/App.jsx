/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:5000/api";

function authHeaders() {
  const token = localStorage.getItem("queueless_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
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
    throw new Error(data.message || data.error || "Request failed");
  }
  return data;
}

export default function App() {
  const [role, setRole] = useState("customer");
  const [backendStatus, setBackendStatus] = useState("checking");
  const [notice, setNotice] = useState("");
  const [token, setToken] = useState(localStorage.getItem("queueless_token") || "");

  const [businessSlug, setBusinessSlug] = useState("demo-clinic");
  const [business, setBusiness] = useState(null);
  const [publicServices, setPublicServices] = useState([]);
  const [queue, setQueue] = useState([]);
  const [queuePaused, setQueuePaused] = useState(false);
  const [booking, setBooking] = useState(null);
  const [trackingCode, setTrackingCode] = useState("");
  const [trackedToken, setTrackedToken] = useState(null);
  // loading state removed to satisfy lint; keep simple UI

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [selectedService, setSelectedService] = useState("");
  const [appointmentTime, setAppointmentTime] = useState("");
  const [mode, setMode] = useState("walkin");

  const [businesses, setBusinesses] = useState([]);
  const [selectedBusinessId, setSelectedBusinessId] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
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
      notify("Business loaded");
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
        data = await api("/public/bookings", { method: "POST", body: JSON.stringify(payload) });
        setBooking({ ...data, type: "appointment" });
      } else {
        data = await api("/public/walk-in", { method: "POST", body: JSON.stringify(payload) });
        setBooking({
          ...data,
          type: "walkin",
          token_number: data.queue_token?.token_number,
          tracking_code: data.queue_token?.tracking_code,
          estimated_wait_minutes: data.queue_token?.estimated_wait_minutes ?? data.estimated_wait_minutes,
        });
      }
      // notify("Request Submitted");
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
      const data = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      localStorage.setItem("queueless_token", data.access_token);
      setToken(data.access_token);
      notify("Login successful");
    } catch (err) {
      notify(err.message);
    }
  };

  // logout handled inline

  const loadBusinesses = async () => {
    try {
      const data = await api("/businesses");
      setBusinesses(data.businesses || []);
      if (!selectedBusinessId && data.businesses?.length) {
        setSelectedBusinessId(data.businesses[0].id);
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
    if (token) {
      loadBusinesses();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (selectedBusinessId) {
      loadBusinessData(selectedBusinessId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBusinessId]);

  const loadQueue = async () => {
    if (!business?.id) return;
    try {
      const data = await api(`/businesses/${business.id}/queue`);
      setQueue(data.queue || data.waiting || []);
      setQueuePaused(data.queue_paused || false);
    } catch (err) {
      notify(err.message);
    }
  };

  const callNext = async () => {
    if (!selectedBusinessId) return;
    try {
      await api(`/businesses/${selectedBusinessId}/queue/call-next`, { method: "POST" });
      await loadBusinessData(selectedBusinessId);
      notify("Next customer called");
    } catch (err) {
      notify(err.message);
    }
  };

  const queueAction = async (tokenId, action) => {
    if (!selectedBusinessId) return;
    try {
      await api(`/businesses/${selectedBusinessId}/queue/${tokenId}/${action}`, { method: "POST" });
      await loadBusinessData(selectedBusinessId);
      notify(`Token ${action} successful`);
    } catch (err) {
      notify(err.message);
    }
  };

  const pauseQueue = async () => {
    if (!selectedBusinessId) return;
    try {
      await api(`/businesses/${selectedBusinessId}/queue/pause`, { method: "POST" });
      setQueuePaused(true);
      notify("Queue paused");
    } catch (err) {
      notify(err.message);
    }
  };

  const resumeQueue = async () => {
    if (!selectedBusinessId) return;
    try {
      await api(`/businesses/${selectedBusinessId}/queue/resume`, { method: "POST" });
      setQueuePaused(false);
      notify("Queue resumed");
    } catch (err) {
      notify(err.message);
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <strong>QueueLess</strong>
        <div>
          <button className="btn btn-secondary" onClick={() => setRole(role === "customer" ? "admin" : "customer")}>
            Switch to {role === "customer" ? "Admin" : "Customer"}
          </button>
          {token && <button className="btn btn-secondary" onClick={() => { localStorage.removeItem("queueless_token"); setToken(""); }}>Logout</button>}
        </div>
      </header>

      <main className="section">
        {notice && <div className="notice success">{notice}</div>}
        <p>Backend: {backendStatus}</p>

        {role === "customer" && (
          <>
            <div className="card">
              <h2>Load Business</h2>
              <input className="input" value={businessSlug} onChange={(e) => setBusinessSlug(e.target.value)} placeholder="Business slug" />
              <button className="btn" onClick={loadPublicBusiness}>Load Business</button>
            </div>

            {business && <div className="card"><h2>Selected: {business.business_name}</h2><p>{business.business_name}</p><p>{business.business_type}</p></div>}

            <div className="card">
              <div className="progress-bar"><div className="progress-fill" style={{ width: booking ? "100%" : "35%" }}></div></div>
              <h2>Book a Queue</h2>
              <form onSubmit={createBooking}>
                <select className="input" value={selectedService} onChange={(e) => setSelectedService(e.target.value)}>
                  <option value="">Select service</option>
                  {publicServices.map((s) => (
                    <option key={s.id} value={s.id}>{s.service_name} ({s.duration_minutes} min)</option>
                  ))}
                </select>
                <input className="input" placeholder="Enter your name" value={customerName} onChange={(e) => setCustomerName(e.target.value)} required />
                <input className="input" placeholder="Enter phone number" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} required />
                <input className="input" placeholder="Email (optional)" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} />
                <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="appointment">Appointment</option>
                  <option value="walkin">Walk-in</option>
                </select>
                {mode === "appointment" && (
                  <input className="input" type="datetime-local" value={appointmentTime} onChange={(e) => setAppointmentTime(e.target.value)} />
                )}
                <button className="btn" type="submit">Submit Booking</button>
              </form>
              {booking && (
                <div className="card" style={{ marginTop: "16px" }}>
                  <h3>Request Submitted</h3>
                  {booking.type === "appointment" && <p>Appointment ID: {booking.appointment?.id}</p>}
                  {booking.type === "walkin" && (
                    <>
                      <p>Token: {booking.token_number}</p>
                      <p>{booking.token_number}</p>
                      <p>Tracking Code: {booking.tracking_code}</p>
                      <p>{booking.tracking_code}</p>
                    </>
                  )}
                  <p>Estimated Wait: {booking.estimated_wait_minutes} minutes</p>
                </div>
              )}
            </div>

            <div className="card">
              <h2>Track Token</h2>
              <form onSubmit={track}>
                <input className="input" placeholder="Enter tracking code" value={trackingCode} onChange={(e) => setTrackingCode(e.target.value)} />
                <button className="btn" type="submit">Track Token</button>
              </form>
              {trackedToken && !trackedToken.error && (
                <div style={{ marginTop: "12px" }}>
                  <h3>Your Token</h3>
                  <p>#{trackedToken.token_number}</p>
                  <p>{trackedToken.queue_status}</p>
                  <p>{trackedToken.customers_ahead}</p>
                  <p>{trackedToken.estimated_wait_minutes} min</p>
                </div>
              )}
              {trackedToken?.error && <p style={{ color: "red" }}>{trackedToken.error}</p>}
            </div>
          </>
        )}

        {role === "admin" && !token && (
          <div className="card">
            <h2>Welcome Back</h2>
            <form onSubmit={login}>
              <input className="input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input className="input" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button className="btn" type="submit">Login</button>
            </form>
          </div>
        )}

        {role === "admin" && token && (
          <>
            <div className="admin-layout">
              <aside className="admin-sidebar">
                <div className="sidebar-brand">QueueLess</div>
                <nav className="sidebar-nav">
                  <span>Dashboard</span>
                  <span>Queues</span>
                  <span>Appointments</span>
                  <span>Services</span>
                  <span>Settings</span>
                </nav>
              </aside>
              <div className="admin-main">
            <div className="card">
              <h2>Queue Management</h2>
              {business && <p>Selected: {business.business_name}</p>}
              <select className="input" value={selectedBusinessId} onChange={(e) => setSelectedBusinessId(e.target.value)}>
                <option value="">Select business</option>
                {businesses.map((b) => (
                  <option key={b.id} value={b.id}>{b.business_name}</option>
                ))}
              </select>
              <button className="btn" onClick={loadPublicBusiness}>Load Business</button>
              <button className="btn" onClick={loadQueue}>Refresh Queue</button>
              <button className="btn" onClick={callNext} disabled={queuePaused}>Call Next</button>
              <button className="btn btn-secondary" onClick={pauseQueue}>Pause Queue</button>
              <button className="btn btn-secondary" onClick={resumeQueue}>Resume Queue</button>
            </div>

            <div className="card">
              <h3>Live Queue</h3>
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
                  {queue.map((q) => (
                    <tr key={q.id}>
                      <td>#{q.token_number}</td>
                      <td>{q.customer_name}</td>
                      <td>{q.status}</td>
                      <td>
                        <button className="btn" onClick={() => queueAction(q.id, "complete")}>Complete</button>
                        <button className="btn" onClick={() => queueAction(q.id, "skip")}>Skip</button>
                        <button className="btn" onClick={() => queueAction(q.id, "cancel")}>Cancel</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}