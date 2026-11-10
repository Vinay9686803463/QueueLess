
import { useEffect, useMemo, useState } from "react";
import "./App.css";

const initialAppointments = [
  { id: 1, token: "A-101", name: "Rahul Sharma", service: "General Consultation", time: "09:30 AM", status: "Serving" },
  { id: 2, token: "A-102", name: "Priya Reddy", service: "General Consultation", time: "09:45 AM", status: "Waiting" },
  { id: 3, token: "A-103", name: "Arjun Kumar", service: "Document Verification", time: "10:00 AM", status: "Waiting" },
  { id: 4, token: "A-104", name: "Sneha Patil", service: "General Consultation", time: "10:15 AM", status: "Waiting" },
  { id: 5, token: "A-105", name: "Kiran Rao", service: "Payment Service", time: "10:30 AM", status: "Completed" },
];

const services = [
  { name: "General Consultation", description: "Get assistance from our service team.", duration: "15 min", icon: "✚", color: "blue" },
  { name: "Document Verification", description: "Submit and verify your documents.", duration: "20 min", icon: "▤", color: "purple" },
  { name: "Payment Service", description: "Billing and payment assistance.", duration: "10 min", icon: "₹", color: "green" },
  { name: "Customer Support", description: "Get help with your questions.", duration: "10 min", icon: "◉", color: "orange" },
];

function Icon({ children }) {
  return <span className="icon" aria-hidden="true">{children}</span>;
}

function App() {
  const [role, setRole] = useState("customer");
  const [page, setPage] = useState("home");
  const [appointments, setAppointments] = useState(initialAppointments);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [selectedService, setSelectedService] = useState(services[0].name);
  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [booking, setBooking] = useState(null);
  const [searchToken, setSearchToken] = useState("");
  const [trackedToken, setTrackedToken] = useState(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;

    fetch("http://127.0.0.1:5000/api/health")
      .then((response) => {
        if (!response.ok) throw new Error("Backend unavailable");
        return response.json();
      })
      .then(() => {
        if (active) setBackendStatus("online");
      })
      .catch(() => {
        if (active) setBackendStatus("offline");
      });

    return () => {
      active = false;
    };
  }, []);

  const waitingCount = appointments.filter((item) => item.status === "Waiting").length;
  const servingCount = appointments.filter((item) => item.status === "Serving").length;
  const completedCount = appointments.filter((item) => item.status === "Completed").length;

  const nextToken = useMemo(() => {
    const numbers = appointments.map((item) => Number(item.token.split("-")[1]) || 100);
    return `A-${Math.max(100, ...numbers) + 1}`;
  }, [appointments]);

  const notify = (message) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 3000);
  };

  const navigate = (nextPage) => {
    setPage(nextPage);
    setBooking(null);
    setTrackedToken(null);
    setNotice("");
  };

  const changeRole = (nextRole) => {
    setRole(nextRole);
    setPage(nextRole === "admin" ? "dashboard" : "home");
    setBooking(null);
    setTrackedToken(null);
  };

  const createBooking = (event) => {
    event.preventDefault();

    if (!customerName.trim() || !customerPhone.trim()) {
      notify("Please enter your name and phone number.");
      return;
    }

    const newAppointment = {
      id: Date.now(),
      token: nextToken,
      name: customerName.trim(),
      service: selectedService,
      time: new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      status: "Waiting",
    };

    setAppointments((current) => [...current, newAppointment]);
    setBooking(newAppointment);
    setSearchToken(newAppointment.token);
    setCustomerName("");
    setCustomerEmail("");
    setCustomerPhone("");
  };

  const trackToken = (event) => {
    event.preventDefault();
    const found = appointments.find(
      (item) => item.token.toLowerCase() === searchToken.trim().toLowerCase()
    );
    setTrackedToken(found || "not-found");
  };

  const updateStatus = (id, status) => {
    setAppointments((current) =>
      current.map((item) => {
        if (item.id === id) return { ...item, status };
        if (status === "Serving" && item.status === "Serving") {
          return { ...item, status: "Waiting" };
        }
        return item;
      })
    );
    notify(`Appointment updated to ${status}.`);
  };

  const callNext = () => {
    const next = appointments.find((item) => item.status === "Waiting");
    if (!next) {
      notify("There are no waiting customers.");
      return;
    }
    setAppointments((current) =>
      current.map((item) => {
        if (item.status === "Serving") return { ...item, status: "Completed" };
        if (item.id === next.id) return { ...item, status: "Serving" };
        return item;
      })
    );
    notify(`Now serving ${next.token}.`);
  };

  const customerNav = [
    { id: "home", label: "Home", icon: "⌂" },
    { id: "book", label: "Book a Queue", icon: "＋" },
    { id: "track", label: "Track Token", icon: "◎" },
  ];

  const adminNav = [
    { id: "dashboard", label: "Dashboard", icon: "▦" },
    { id: "queue", label: "Live Queue", icon: "☷" },
    { id: "appointments", label: "Appointments", icon: "▣" },
    { id: "services", label: "Services", icon: "◇" },
  ];

  const navItems = role === "admin" ? adminNav : customerNav;

  const getAheadCount = (appointment) => {
    if (appointment.status === "Completed") return 0;
    if (appointment.status === "Serving") return 0;
    const waiting = appointments.filter((item) => item.status === "Waiting");
    return waiting.findIndex((item) => item.id === appointment.id);
  };

  const statusClass = (status) => status.toLowerCase();

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => navigate(role === "admin" ? "dashboard" : "home")}>
          <span className="brand-mark">Q</span>
          <span>Queue<span className="brand-light">Less</span></span>
        </button>

        <nav className="top-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`top-nav-link ${page === item.id ? "active" : ""}`}
              onClick={() => navigate(item.id)}
            >
              <Icon>{item.icon}</Icon>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="top-actions">
          <div className="role-switch">
            <button className={role === "customer" ? "selected" : ""} onClick={() => changeRole("customer")}>
              Customer
            </button>
            <button className={role === "admin" ? "selected" : ""} onClick={() => changeRole("admin")}>
              Admin
            </button>
          </div>
          <div className="avatar">{role === "admin" ? "AD" : "GU"}</div>
        </div>
      </header>

      <main className="main-content">
        {notice && <div className="toast">{notice}</div>}

        <div className="environment-row">
          <span className={`connection-dot ${backendStatus}`}></span>
          {backendStatus === "online" ? "Backend connected" : backendStatus === "checking" ? "Checking backend..." : "Demo mode · Backend unavailable"}
          <span className="environment-divider">•</span>
          <span>QueueLess Preview</span>
        </div>

        {role === "customer" && page === "home" && (
          <>
            <section className="hero">
              <div className="hero-copy">
                <span className="eyebrow"><span className="eyebrow-dot"></span> SMART QUEUE MANAGEMENT</span>
                <h1>Skip the wait.<br /><span>Own your time.</span></h1>
                <p>Book your place in the queue from anywhere. Track your token in real time and spend less time waiting.</p>
                <div className="hero-buttons">
                  <button className="button button-primary" onClick={() => navigate("book")}>Book your queue <span>→</span></button>
                  <button className="button button-secondary" onClick={() => navigate("track")}>Track your token</button>
                </div>
                <div className="hero-proof">
                  <span className="proof-icon">✓</span>
                  Simple booking
                  <span className="proof-icon">✓</span>
                  Less waiting
                  <span className="proof-icon">✓</span>
                  Easy tracking
                </div>
              </div>
              <div className="hero-visual">
                <div className="visual-orbit orbit-one"></div>
                <div className="visual-orbit orbit-two"></div>
                <div className="floating-card floating-top">
                  <span className="floating-icon green-icon">✓</span>
                  <div><strong>Booking confirmed</strong><small>Your place is reserved</small></div>
                </div>
                <div className="ticket-card">
                  <div className="ticket-head"><span>YOUR QUEUE TOKEN</span><span className="ticket-live">● LIVE</span></div>
                  <div className="ticket-number">A-102</div>
                  <div className="ticket-divider"></div>
                  <div className="ticket-stats">
                    <div><small>People ahead</small><strong>02</strong></div>
                    <div><small>Est. wait</small><strong>15 min</strong></div>
                  </div>
                  <div className="ticket-progress"><span></span></div>
                  <small className="ticket-caption">We'll keep your place in line.</small>
                </div>
                <div className="floating-card floating-bottom">
                  <span className="floating-icon blue-icon">◷</span>
                  <div><strong>Save your time</strong><small>Wait smarter, not longer</small></div>
                </div>
                <div className="hero-circle"></div>
              </div>
            </section>

            <section className="stats-strip">
              <div><strong>{appointments.length.toString().padStart(2, "0")}</strong><span>Today's bookings</span></div>
              <div><strong>{waitingCount.toString().padStart(2, "0")}</strong><span>Currently waiting</span></div>
              <div><strong>{servingCount.toString().padStart(2, "0")}</strong><span>Being served</span></div>
              <div><strong>{completedCount.toString().padStart(2, "0")}</strong><span>Completed</span></div>
            </section>

            <section className="section-block">
              <div className="section-heading">
                <div><span className="eyebrow">HOW IT WORKS</span><h2>Queueing made simple</h2><p>Three easy steps to a better experience.</p></div>
              </div>
              <div className="steps-grid">
                <div className="step-card"><span className="step-number">01</span><div className="step-icon">▤</div><h3>Choose a service</h3><p>Select the service you need and enter your details.</p></div>
                <div className="step-card"><span className="step-number">02</span><div className="step-icon">▣</div><h3>Get your token</h3><p>Receive a unique queue number after booking.</p></div>
                <div className="step-card"><span className="step-number">03</span><div className="step-icon">◷</div><h3>Track your turn</h3><p>Check your position and estimated waiting time.</p></div>
              </div>
            </section>

            <section className="cta-banner">
              <div><span className="eyebrow">READY WHEN YOU ARE</span><h2>Your time matters. Start here.</h2><p>Join the queue without standing in one.</p></div>
              <button className="button button-white" onClick={() => navigate("book")}>Get a token <span>→</span></button>
            </section>
          </>
        )}

        {role === "customer" && page === "book" && (
          <section className="page-section narrow-section">
            <button className="back-link" onClick={() => navigate("home")}>← Back to home</button>
            <div className="page-title"><span className="eyebrow">CUSTOMER PORTAL</span><h1>Book your queue</h1><p>Choose a service and reserve your place. It only takes a moment.</p></div>
            {booking ? (
              <div className="confirmation-card">
                <div className="success-circle">✓</div>
                <span className="eyebrow">BOOKING CONFIRMED</span>
                <h2>Your token is ready!</h2>
                <p>Keep this token handy to track your queue position.</p>
                <div className="confirmed-token">{booking.token}</div>
                <div className="confirmation-details"><span>Customer</span><strong>{booking.name}</strong><span>Service</span><strong>{booking.service}</strong><span>Booking time</span><strong>{booking.time}</strong><span>Status</span><strong className="status waiting">Waiting</strong></div>
                <button className="button button-primary full-button" onClick={() => { setSearchToken(booking.token); setBooking(null); navigate("track"); }}>Track my token →</button>
              </div>
            ) : (
              <form className="form-card" onSubmit={createBooking}>
                <div className="form-heading"><span className="form-step">1</span><div><h2>Select a service</h2><p>What would you like help with?</p></div></div>
                <div className="service-select-grid">
                  {services.map((service) => (
                    <button type="button" key={service.name} className={`service-option ${selectedService === service.name ? "chosen" : ""}`} onClick={() => setSelectedService(service.name)}>
                      <span className={`service-icon ${service.color}`}>{service.icon}</span>
                      <span className="service-option-text"><strong>{service.name}</strong><small>{service.duration} · {service.description}</small></span>
                      <span className="radio-check">{selectedService === service.name ? "✓" : ""}</span>
                    </button>
                  ))}
                </div>
                <div className="form-divider"></div>
                <div className="form-heading"><span className="form-step">2</span><div><h2>Your details</h2><p>Enter your contact information.</p></div></div>
                <div className="input-grid">
                  <label className="field full-field">Full name<input value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Enter your full name" required /></label>
                  <label className="field">Phone number<input type="tel" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="Enter phone number" required /></label>
                  <label className="field">Email address <span className="optional">(optional)</span><input type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} placeholder="you@example.com" /></label>
                </div>
                <div className="form-note"><span>🔒</span> Your details are used only for this booking.</div>
                <button className="button button-primary full-button" type="submit">Confirm booking <span>→</span></button>
              </form>
            )}
          </section>
        )}

        {role === "customer" && page === "track" && (
          <section className="page-section narrow-section">
            <button className="back-link" onClick={() => navigate("home")}>← Back to home</button>
            <div className="page-title"><span className="eyebrow">QUEUE TRACKER</span><h1>Track your token</h1><p>Enter your token number to see your current queue position.</p></div>
            <form className="track-search" onSubmit={trackToken}>
              <label className="field">Your token number<input value={searchToken} onChange={(e) => { setSearchToken(e.target.value); setTrackedToken(null); }} placeholder="e.g. A-102" required /></label>
              <button className="button button-primary" type="submit">Track token →</button>
            </form>
            {trackedToken === "not-found" && <div className="empty-state">We couldn't find that token. Please check the number and try again.</div>}
            {trackedToken && trackedToken !== "not-found" && (
              <div className="tracking-card">
                <div className="tracking-top"><div><span className="eyebrow">YOUR TOKEN</span><h2>{trackedToken.token}</h2></div><span className={`status ${statusClass(trackedToken.status)}`}>{trackedToken.status}</span></div>
                <div className="tracking-info"><div><small>Customer</small><strong>{trackedToken.name}</strong></div><div><small>Service</small><strong>{trackedToken.service}</strong></div></div>
                <div className="position-box">
                  <div><small>People ahead of you</small><strong>{trackedToken.status === "Serving" ? "It's your turn!" : trackedToken.status === "Completed" ? "Completed" : getAheadCount(trackedToken)}</strong></div>
                  <div><small>Estimated wait</small><strong>{trackedToken.status === "Serving" || trackedToken.status === "Completed" ? "0 min" : `${getAheadCount(trackedToken) * 15} min`}</strong></div>
                </div>
                <div className="tracking-message">{trackedToken.status === "Serving" ? "Please proceed to the service counter." : trackedToken.status === "Completed" ? "Your appointment has been completed." : "You're in the queue. We'll be ready for you soon."}</div>
              </div>
            )}
            <div className="help-card"><span className="help-icon">i</span><div><strong>Where can I find my token?</strong><p>Your token number is shown on the confirmation screen after booking.</p></div></div>
          </section>
        )}

        {role === "admin" && page === "dashboard" && (
          <section className="admin-page">
            <div className="admin-heading"><div><span className="eyebrow">OVERVIEW</span><h1>Good day, Admin <span>👋</span></h1><p>Here's what's happening with your queue today.</p></div><button className="button button-primary" onClick={callNext}>Call next customer →</button></div>
            <div className="admin-stats">
              <div className="metric-card"><div className="metric-top"><span>Total appointments</span><span className="metric-icon blue">▣</span></div><strong>{appointments.length}</strong><small>Today's bookings</small></div>
              <div className="metric-card"><div className="metric-top"><span>Waiting customers</span><span className="metric-icon orange">◷</span></div><strong>{waitingCount}</strong><small>In the queue</small></div>
              <div className="metric-card"><div className="metric-top"><span>Currently serving</span><span className="metric-icon green">◉</span></div><strong>{servingCount}</strong><small>At the counter</small></div>
              <div className="metric-card"><div className="metric-top"><span>Completed</span><span className="metric-icon purple">✓</span></div><strong>{completedCount}</strong><small>Finished today</small></div>
            </div>
            <div className="admin-content-grid">
              <div className="panel queue-panel">
                <div className="panel-heading"><div><h2>Live queue</h2><p>Manage your current customers.</p></div><button className="text-button" onClick={() => navigate("queue")}>View all →</button></div>
                <AppointmentTable appointments={appointments.slice(0, 5)} updateStatus={updateStatus} compact />
              </div>
              <div className="panel activity-panel">
                <div className="panel-heading"><div><h2>Queue summary</h2><p>Today's activity</p></div></div>
                <div className="summary-row"><span className="summary-bullet waiting-bullet"></span><span>Waiting</span><strong>{waitingCount}</strong></div>
                <div className="summary-row"><span className="summary-bullet serving-bullet"></span><span>Serving</span><strong>{servingCount}</strong></div>
                <div className="summary-row"><span className="summary-bullet completed-bullet"></span><span>Completed</span><strong>{completedCount}</strong></div>
                <div className="summary-total"><span>Total appointments</span><strong>{appointments.length}</strong></div>
                <button className="button button-secondary full-button" onClick={() => navigate("appointments")}>Manage appointments</button>
              </div>
            </div>
          </section>
        )}

        {role === "admin" && (page === "queue" || page === "appointments") && (
          <section className="admin-page">
            <div className="admin-heading"><div><span className="eyebrow">MANAGEMENT</span><h1>{page === "queue" ? "Live Queue" : "Appointments"}</h1><p>View and manage customer appointments.</p></div><button className="button button-primary" onClick={callNext}>Call next customer →</button></div>
            <div className="admin-stats compact-stats">
              <div className="metric-card"><span>Waiting</span><strong>{waitingCount}</strong></div>
              <div className="metric-card"><span>Serving</span><strong>{servingCount}</strong></div>
              <div className="metric-card"><span>Completed</span><strong>{completedCount}</strong></div>
            </div>
            <div className="panel table-panel"><div className="panel-heading"><div><h2>All appointments</h2><p>{appointments.length} appointments in this demo session</p></div><span className="live-label">● LIVE VIEW</span></div><AppointmentTable appointments={appointments} updateStatus={updateStatus} /></div>
          </section>
        )}

        {role === "admin" && page === "services" && (
          <section className="admin-page">
            <div className="admin-heading"><div><span className="eyebrow">MANAGEMENT</span><h1>Services</h1><p>Services currently available for customer bookings.</p></div></div>
            <div className="services-admin-grid">{services.map((service) => <div className="admin-service-card" key={service.name}><span className={`service-icon ${service.color}`}>{service.icon}</span><h3>{service.name}</h3><p>{service.description}</p><div className="service-duration">◷ {service.duration}</div><span className="service-active">● Active</span></div>)}</div>
          </section>
        )}

        <footer className="footer"><div className="footer-brand"><span className="brand-mark">Q</span> QueueLess</div><span>Making every minute count.</span><span>© 2026 QueueLess</span></footer>
      </main>
    </div>
  );
}

function AppointmentTable({ appointments, updateStatus, compact = false }) {
  if (!appointments.length) {
    return <div className="empty-state">No appointments yet. New customer bookings will appear here.</div>;
  }

  return (
    <div className="table-scroll">
      <table className="appointment-table">
        <thead><tr><th>Token</th><th>Customer</th>{!compact && <th>Service</th>}<th>Time</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>
          {appointments.map((item) => (
            <tr key={item.id}>
              <td><strong className="token-cell">{item.token}</strong></td>
              <td><span className="customer-cell">{item.name}</span></td>
              {!compact && <td>{item.service}</td>}
              <td>{item.time}</td>
              <td><span className={`status ${item.status.toLowerCase()}`}>{item.status}</span></td>
              <td>
                <select className="status-select" value={item.status} onChange={(e) => updateStatus(item.id, e.target.value)} aria-label={`Change status for ${item.token}`}>
                  <option>Waiting</option><option>Serving</option><option>Completed</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
