/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:5000/api";

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, options = {}, token = "") {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
      ...authHeaders(token),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || data.error || "Request failed");
  return data;
}

function loginErrorMessage(error) {
  const message = error instanceof Error ? error.message.trim() : "";
  if (/^invalid email or password\.?$/i.test(message)) {
    return "Invalid email or password.";
  }
  if (
    !message ||
    ["request failed", "failed to fetch", "fetch failed"].includes(
      message.toLowerCase()
    )
  ) {
    return "Unable to sign in right now. Please try again.";
  }
  return message;
}

function LoginError({ message }) {
  if (!message) return null;
  return (
    <div className="login-error" role="alert">
      <span className="login-error-icon" aria-hidden="true">!</span>
      <span>{message}</span>
    </div>
  );
}

function PasswordRecoveryPanel({
  portal,
  stage,
  email,
  otp,
  newPassword,
  confirmPassword,
  showNewPassword,
  showConfirmPassword,
  loading,
  cooldown,
  error,
  message,
  onEmailChange,
  onOtpChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onToggleNewPassword,
  onToggleConfirmPassword,
  onSendOtp,
  onVerifyOtp,
  onResendOtp,
  onChangePassword,
  onBack,
}) {
  const portalLabel = portal === "admin" ? "administrator" : "customer";

  return (
    <div className="password-recovery-panel">
      {message && <p className="recovery-message" role="status">{message}</p>}
      <LoginError message={error} />

      {stage === "forgot" && (
        <form onSubmit={onSendOtp}>
          <label htmlFor={`${portal}-recovery-email`}>Registered email address</label>
          <input
            id={`${portal}-recovery-email`}
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => onEmailChange(event.target.value)}
            required
          />
          <button className="btn btn-admin-login" type="submit" disabled={loading}>
            {loading ? "Sending OTP..." : "Send OTP"}
          </button>
          <button className="recovery-back-button" type="button" onClick={onBack}>
            Back to {portal === "admin" ? "admin" : "customer"} login
          </button>
        </form>
      )}

      {stage === "otp" && (
        <>
          <p className="recovery-instructions">
            Enter the six-digit code sent to <strong>{email}</strong> for your {portalLabel} account.
          </p>
          <form onSubmit={onVerifyOtp}>
            <label htmlFor={`${portal}-recovery-otp`}>Verification code</label>
            <input
              id={`${portal}-recovery-otp`}
              className="input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={otp}
              onChange={(event) => onOtpChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
              required
            />
            <button className="btn btn-admin-login" type="submit" disabled={loading}>
              {loading ? "Verifying..." : "Verify OTP"}
            </button>
          </form>
          <button
            className="recovery-secondary-button"
            type="button"
            onClick={onResendOtp}
            disabled={loading || cooldown > 0}
          >
            {cooldown > 0 ? `Resend OTP in ${cooldown}s` : "Resend OTP"}
          </button>
          <button className="recovery-back-button" type="button" onClick={onBack}>
            Back to login
          </button>
        </>
      )}

      {stage === "change" && (
        <form onSubmit={onChangePassword}>
          <label htmlFor={`${portal}-new-password`}>New Password</label>
          <div className="recovery-password-field">
            <input
              id={`${portal}-new-password`}
              className="input"
              type={showNewPassword ? "text" : "password"}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              value={newPassword}
              onChange={(event) => onNewPasswordChange(event.target.value)}
              required
            />
            <button
              type="button"
              className="recovery-password-toggle"
              onClick={onToggleNewPassword}
              aria-label={showNewPassword ? "Hide new password" : "Show new password"}
            >
              {showNewPassword ? "Hide" : "Show"}
            </button>
          </div>
          <label htmlFor={`${portal}-confirm-password`}>Confirm Password</label>
          <div className="recovery-password-field">
            <input
              id={`${portal}-confirm-password`}
              className="input"
              type={showConfirmPassword ? "text" : "password"}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              value={confirmPassword}
              onChange={(event) => onConfirmPasswordChange(event.target.value)}
              required
            />
            <button
              type="button"
              className="recovery-password-toggle"
              onClick={onToggleConfirmPassword}
              aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
            >
              {showConfirmPassword ? "Hide" : "Show"}
            </button>
          </div>
          <button className="btn btn-admin-login" type="submit" disabled={loading}>
            {loading ? "Changing password..." : "Change your password"}
          </button>
          <button className="recovery-back-button" type="button" onClick={onBack}>
            Back to login
          </button>
        </form>
      )}
    </div>
  );
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
  const [role, setRole] = useState(
    () => sessionStorage.getItem("queueless_portal") === "admin" ? "admin" : "customer"
  );
  const [backendStatus, setBackendStatus] = useState("checking");
  const [notice, setNotice] = useState("");
  const [token, setToken] = useState("");
  const [customerToken, setCustomerToken] = useState("");
  const [customerAppointments, setCustomerAppointments] = useState([]);
  const [customerTokens, setCustomerTokens] = useState([]);

  const [businessSlug, setBusinessSlug] = useState("demo-clinic");
  const [business, setBusiness] = useState(null);
  const [publicServices, setPublicServices] = useState([]);
  const [adminServices, setAdminServices] = useState([]);
  const [queue, setQueue] = useState([]);
  const [queuePaused, setQueuePaused] = useState(false);
  const [booking, setBooking] = useState(null);
  const [trackingCode, setTrackingCode] = useState("");
  const [trackedToken, setTrackedToken] = useState(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [adminLoginError, setAdminLoginError] = useState("");
  const [customerLoginError, setCustomerLoginError] = useState("");
  const [adminLoginLoading, setAdminLoginLoading] = useState(false);
  const [customerLoginLoading, setCustomerLoginLoading] = useState(false);
  const adminLoginInFlight = useRef(false);
  const customerLoginInFlight = useRef(false);
  const [recoveryStage, setRecoveryStage] = useState("login");
  const [recoveryOtp, setRecoveryOtp] = useState("");
  const [resetAuthorization, setResetAuthorization] = useState("");
  const [newResetPassword, setNewResetPassword] = useState("");
  const [confirmResetPassword, setConfirmResetPassword] = useState("");
  const [showNewResetPassword, setShowNewResetPassword] = useState(false);
  const [showConfirmResetPassword, setShowConfirmResetPassword] = useState(false);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const recoveryInFlight = useRef(false);
  const [recoveryCooldown, setRecoveryCooldown] = useState(0);
  const [recoveryError, setRecoveryError] = useState("");
  const [recoveryMessage, setRecoveryMessage] = useState("");
  const [passwordChanged, setPasswordChanged] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showRegister, setShowRegister] = useState(false);
  const [customerAuthMode, setCustomerAuthMode] = useState("login");
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
    localStorage.removeItem("queueless_token");
    localStorage.removeItem("queueless_customer_token");
  }, []);

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

  useEffect(() => {
    if (recoveryCooldown <= 0) return undefined;
    const timer = window.setTimeout(
      () => setRecoveryCooldown((seconds) => Math.max(0, seconds - 1)),
      1000
    );
    return () => window.clearTimeout(timer);
  }, [recoveryCooldown]);

  const clearPasswordRecovery = () => {
    setRecoveryStage("login");
    setRecoveryOtp("");
    setResetAuthorization("");
    setNewResetPassword("");
    setConfirmResetPassword("");
    setShowNewResetPassword(false);
    setShowConfirmResetPassword(false);
    setRecoveryLoading(false);
    setRecoveryCooldown(0);
    setRecoveryError("");
    setRecoveryMessage("");
  };

  const returnToLogin = () => {
    clearPasswordRecovery();
    setShowRegister(false);
    setCustomerAuthMode("login");
  };

  const startPasswordRecovery = () => {
    setRecoveryStage("forgot");
    setRecoveryOtp("");
    setResetAuthorization("");
    setNewResetPassword("");
    setConfirmResetPassword("");
    setRecoveryError("");
    setRecoveryMessage("");
  };

  const sendPasswordResetOtp = async (event) => {
    event.preventDefault();
    if (recoveryInFlight.current) return;

    const portal = role;
    const recoveryEmail = portal === "admin" ? email : customerEmail;
    const prefix = portal === "admin" ? "auth" : "customer-auth";
    recoveryInFlight.current = true;
    setRecoveryLoading(true);
    setRecoveryError("");
    setRecoveryMessage("");

    try {
      const data = await api(`/${prefix}/forgot-password`, {
        method: "POST",
        body: JSON.stringify({ email: recoveryEmail }),
      });
      setRecoveryStage("otp");
      setRecoveryMessage(data.message || "If the email matches an active account in this portal, a verification code will be sent.");
      setRecoveryCooldown(60);
    } catch (error) {
      setRecoveryError(error.message);
    } finally {
      recoveryInFlight.current = false;
      setRecoveryLoading(false);
    }
  };

  const verifyPasswordResetOtp = async (event) => {
    event.preventDefault();
    if (recoveryInFlight.current) return;

    const portal = role;
    const recoveryEmail = portal === "admin" ? email : customerEmail;
    const prefix = portal === "admin" ? "auth" : "customer-auth";
    recoveryInFlight.current = true;
    setRecoveryLoading(true);
    setRecoveryError("");
    setRecoveryMessage("");

    try {
      const data = await api(`/${prefix}/verify-otp`, {
        method: "POST",
        body: JSON.stringify({ email: recoveryEmail, otp: recoveryOtp }),
      });
      if (!data.reset_token) {
        throw new Error("Unable to verify the code. Please request a new one.");
      }
      setResetAuthorization(data.reset_token);
      setRecoveryStage("change");
      setRecoveryMessage("");
    } catch (error) {
      setRecoveryError(error.message);
    } finally {
      recoveryInFlight.current = false;
      setRecoveryLoading(false);
    }
  };

  const changePassword = async (event) => {
    event.preventDefault();
    if (recoveryInFlight.current) return;
    setRecoveryError("");
    if (newResetPassword.length < 8) {
      setRecoveryError("Password must be at least 8 characters.");
      return;
    }
    if (newResetPassword !== confirmResetPassword) {
      setRecoveryError("The passwords do not match.");
      return;
    }
    if (!resetAuthorization) {
      setRecoveryError("Your reset authorization has expired. Request a new code.");
      return;
    }

    const prefix = role === "admin" ? "auth" : "customer-auth";
    recoveryInFlight.current = true;
    setRecoveryLoading(true);
    try {
      await api(`/${prefix}/reset-password`, {
        method: "POST",
        body: JSON.stringify({
          token: resetAuthorization,
          password: newResetPassword,
        }),
      });
      if (role === "admin") {
        setToken("");
      } else {
        setCustomerToken("");
        setCustomerAppointments([]);
        setCustomerTokens([]);
      }
      setRecoveryStage("login");
      setRecoveryOtp("");
      setResetAuthorization("");
      setNewResetPassword("");
      setConfirmResetPassword("");
      setPassword("");
      setCustomerPassword("");
      setRecoveryCooldown(0);
      setRecoveryMessage("");
      setRecoveryError("");
      setPasswordChanged(true);
    } catch (error) {
      setRecoveryError(error.message);
    } finally {
      recoveryInFlight.current = false;
      setRecoveryLoading(false);
    }
  };

  const loadPublicBusiness = async () => {
    try {
      const biz = await api(`/public/business/${businessSlug}`);
      setBusiness(biz.business);

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

        data = await api(
          "/public/bookings",
          { method: "POST", body: JSON.stringify(payload) },
          customerToken
        );

        setBooking({ ...data, type: "appointment" });
      } else {
        data = await api(
          "/public/walk-in",
          { method: "POST", body: JSON.stringify(payload) },
          customerToken
        );

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
    if (adminLoginInFlight.current) return;

    adminLoginInFlight.current = true;
    setAdminLoginLoading(true);
    setAdminLoginError("");
    setToken("");

    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });

      if (!data.access_token) {
        throw new Error("Unable to sign in right now. Please try again.");
      }
      setToken(data.access_token);
      notify("Login successful");
    } catch (err) {
      setToken("");
      setAdminLoginError(loginErrorMessage(err));
    } finally {
      adminLoginInFlight.current = false;
      setAdminLoginLoading(false);
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
      setToken(data.access_token);
      notify("Registration successful");
      setShowRegister(false);
    } catch (err) {
      notify(err.message);
    }
  };

  const loadCustomerAccount = async (authToken) => {
    const [appointments, queueTokens] = await Promise.all([
      api("/customer-auth/appointments", {}, authToken),
      api("/customer-auth/queue-tokens", {}, authToken),
    ]);
    setCustomerAppointments(appointments.appointments || []);
    setCustomerTokens(queueTokens.tokens || []);
  };

  const customerLogin = async (e) => {
    e.preventDefault();
    if (customerLoginInFlight.current) return;

    customerLoginInFlight.current = true;
    setCustomerLoginLoading(true);
    setCustomerLoginError("");
    setCustomerToken("");
    setCustomerAppointments([]);
    setCustomerTokens([]);

    try {
      const data = await api("/customer-auth/login", { method: "POST", body: JSON.stringify({ email: customerEmail, password: customerPassword }) });
      if (!data.access_token) {
        throw new Error("Unable to sign in right now. Please try again.");
      }
      setCustomerToken(data.access_token);
      notify("Customer login successful");
      try {
        await loadCustomerAccount(data.access_token);
      } catch (err) {
        notify(err.message);
      }
    } catch (err) {
      setCustomerToken("");
      setCustomerLoginError(loginErrorMessage(err));
    } finally {
      customerLoginInFlight.current = false;
      setCustomerLoginLoading(false);
    }
  };

  const customerRegister = async (e) => {
    e.preventDefault();
    try {
      const data = await api("/customer-auth/register", { method: "POST", body: JSON.stringify({ full_name: customerName, email: customerEmail, phone: customerPhone, password: customerPassword }) });
      setCustomerToken(data.access_token);
      notify("Customer registration successful");
      try {
        await loadCustomerAccount(data.access_token);
      } catch (err) {
        notify(err.message);
      }
    } catch (err) {
      notify(err.message);
    }
  };

  const customerLogout = () => {
    setCustomerToken("");
    setCustomerAppointments([]);
    setCustomerTokens([]);
    notify("You have been logged out");
  };

  const logout = () => {
    setToken("");
    setBusinesses([]);
    setSelectedBusinessId("");
    setQueue([]);
    setAdminServices([]);
    notify("You have been logged out");
  };

  const loadBusinesses = async () => {
    try {
      const data = await api("/businesses", {}, token);
      const list = data.businesses || [];

      setBusinesses(list);

      if (!selectedBusinessId && list.length) {
        setSelectedBusinessId(list[0].id);
      }
    } catch (err) {
      notify(err.message);
    }
  };

  const loadBusinessData = async (businessId, authToken = token) => {
    if (!businessId) return;

    try {
      const [svc, q] = await Promise.all([
        api(`/businesses/${businessId}/services`, {}, authToken),
        api(`/businesses/${businessId}/queue`, {}, authToken),
      ]);

      setAdminServices(svc.services || []);
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
        `/businesses/${selectedBusinessId}/queue`,
        {},
        token
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
        { method: "POST" },
        token
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
        { method: "POST" },
        token
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
        { method: "POST" },
        token
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
        { method: "POST" },
        token
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
            disabled={adminLoginLoading || customerLoginLoading || recoveryLoading}
            onClick={() => {
              const nextRole = role === "customer" ? "admin" : "customer";
              sessionStorage.setItem("queueless_portal", nextRole);
              setRole(nextRole);
              returnToLogin();
              setAdminLoginError("");
              setCustomerLoginError("");
            }}
          >
            {role === "customer"
              ? "Switch to Admin Portal"
              : "Switch to Customer Portal"}
          </button>

          {((role === "admin" && token) ||
            (role === "customer" && customerToken)) && (
            <button
              className="btn btn-logout"
              onClick={role === "admin" ? logout : customerLogout}
            >
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

      {role === "customer" && !customerToken && (
        <main className="login-page customer-login-page">
          <div className="login-art">
            <div className="login-art-orbit" />
            <div className="login-art-card">
              <span>Q</span>
              <strong>QueueLess</strong>
              <p>
                Your time matters.
                <br />
                Stay in control of every visit.
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

          <section className="login-card customer-login-card">
            <span className="eyebrow">CUSTOMER PORTAL</span>
            <h1>
              {recoveryStage === "login"
                ? customerAuthMode === "login"
                  ? "Welcome back"
                  : "Create your account"
                : recoveryStage === "forgot"
                  ? "Forgot Password"
                  : recoveryStage === "otp"
                    ? "Verify OTP"
                    : "Change Password"}
            </h1>
            <p>
              {recoveryStage !== "login"
                ? "Securely recover access to your customer account."
                : customerAuthMode === "login"
                  ? "Sign in to book visits and track your place in line."
                  : "Register to manage your appointments and queue tokens."}
            </p>

            {recoveryStage === "login" ? (
              <form
                onSubmit={
                  customerAuthMode === "login"
                    ? customerLogin
                    : customerRegister
                }
              >
              {customerAuthMode === "register" && (
                <>
                  <label htmlFor="customer-register-name">Full name</label>
                  <input
                    id="customer-register-name"
                    className="input"
                    autoComplete="name"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    required
                  />
                  <label htmlFor="customer-register-phone">Phone number</label>
                  <input
                    id="customer-register-phone"
                    className="input"
                    type="tel"
                    autoComplete="tel"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                  />
                </>
              )}

              <label htmlFor="customer-email">Email address</label>
              <input
                id="customer-email"
                className="input"
                type="email"
                autoComplete="email"
                disabled={customerLoginLoading}
                value={customerEmail}
                onChange={(e) => {
                  setCustomerEmail(e.target.value);
                  setCustomerLoginError("");
                }}
                required
              />
              <label htmlFor="customer-password">Password</label>
              <input
                id="customer-password"
                className="input"
                type="password"
                disabled={customerLoginLoading}
                autoComplete={
                  customerAuthMode === "login"
                    ? "current-password"
                    : "new-password"
                }
                value={customerPassword}
                onChange={(e) => {
                  setCustomerPassword(e.target.value);
                  setCustomerLoginError("");
                }}
                required
              />
              {customerAuthMode === "login" && (
                <LoginError message={customerLoginError} />
              )}
              <button
                className="btn btn-admin-login"
                type="submit"
                disabled={customerAuthMode === "login" && customerLoginLoading}
              >
                {customerAuthMode === "login"
                  ? customerLoginLoading
                    ? "Signing in..."
                    : "Sign in to customer portal"
                  : "Register"}
                {customerAuthMode === "login" && customerLoginLoading ? (
                  <span className="login-spinner" aria-hidden="true" />
                ) : (
                  <span aria-hidden="true">→</span>
                )}
              </button>
              </form>
            ) : (
              <PasswordRecoveryPanel
                portal="customer"
                stage={recoveryStage}
                email={customerEmail}
                otp={recoveryOtp}
                newPassword={newResetPassword}
                confirmPassword={confirmResetPassword}
                showNewPassword={showNewResetPassword}
                showConfirmPassword={showConfirmResetPassword}
                loading={recoveryLoading}
                cooldown={recoveryCooldown}
                error={recoveryError}
                message={recoveryMessage}
                onEmailChange={(value) => {
                  setCustomerEmail(value);
                  setRecoveryError("");
                }}
                onOtpChange={(value) => {
                  setRecoveryOtp(value);
                  setRecoveryError("");
                }}
                onNewPasswordChange={(value) => {
                  setNewResetPassword(value);
                  setRecoveryError("");
                }}
                onConfirmPasswordChange={(value) => {
                  setConfirmResetPassword(value);
                  setRecoveryError("");
                }}
                onToggleNewPassword={() => setShowNewResetPassword((value) => !value)}
                onToggleConfirmPassword={() => setShowConfirmResetPassword((value) => !value)}
                onSendOtp={sendPasswordResetOtp}
                onVerifyOtp={verifyPasswordResetOtp}
                onResendOtp={sendPasswordResetOtp}
                onChangePassword={changePassword}
                onBack={returnToLogin}
              />
            )}

            {recoveryStage === "login" && (
              <div className="login-secondary-actions">
                <button
                  className="btn btn-secondary"
                  type="button"
                  disabled={customerLoginLoading}
                  onClick={() => {
                    setCustomerLoginError("");
                    setCustomerAuthMode((mode) =>
                      mode === "login" ? "register" : "login"
                    );
                  }}
                >
                  {customerAuthMode === "login"
                    ? "Create customer account"
                    : "Back to customer login"}
                </button>
                {customerAuthMode === "login" && (
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={startPasswordRecovery}
                  >
                    Forgot password
                  </button>
                )}
              </div>
            )}
            <small className="login-footnote">
              Secure access for QueueLess customers.
            </small>
          </section>
        </main>
      )}

      {role === "customer" && customerToken && (
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
                Keep track of your visits, appointments and queue tokens.
              </p>
              <section className="customer-account" aria-labelledby="customer-account-title">
                <h3 id="customer-account-title">Customer Account</h3>
                <div className="customer-account-summary">
                  <p>You’re signed in. Your appointments and queue tokens are below.</p>
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

          <section className="login-card">
            <span className="eyebrow">ADMINISTRATOR ACCESS</span>
            <h1>
              {recoveryStage === "login"
                ? showRegister ? "Create your account" : "Welcome back"
                : recoveryStage === "forgot"
                  ? "Forgot Password"
                  : recoveryStage === "otp"
                    ? "Verify OTP"
                    : "Change Password"}
            </h1>
            <p>
              {recoveryStage !== "login"
                ? "Securely recover access to your administrator account."
                : showRegister
                  ? "Register your QueueLess administrator account."
                  : "Sign in to manage your business queue."}
            </p>

            {recoveryStage === "login" && !showRegister && (
              <form onSubmit={login}>
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                className="input"
                type="email"
                placeholder="admin@example.com"
                disabled={adminLoginLoading}
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setAdminLoginError("");
                }}
                required
              />

              <label htmlFor="password">Password</label>
              <div style={{ position: "relative" }}>
                <input
                  id="password"
                  className="input"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  disabled={adminLoginLoading}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setAdminLoginError("");
                  }}
                  required
                />
                <button
                  type="button"
                  disabled={adminLoginLoading}
                  onClick={() => setShowPassword((v) => !v)}
                  style={{ position: "absolute", right: "10px", top: "10px", border: "none", background: "transparent", cursor: "pointer" }}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>

              <LoginError message={adminLoginError} />
              <button
                className="btn btn-admin-login"
                type="submit"
                disabled={adminLoginLoading}
              >
                {adminLoginLoading ? "Signing in..." : "Sign in to dashboard"}
                {adminLoginLoading ? (
                  <span className="login-spinner" aria-hidden="true" />
                ) : (
                  <span aria-hidden="true">→</span>
                )}
              </button>
              </form>
            )}

            {recoveryStage === "login" && showRegister && (
              <form className="portal-register-form" onSubmit={register}>
              <input className="input" placeholder="Full name" value={regName} onChange={(e) => setRegName(e.target.value)} required />
              <input className="input" type="email" placeholder="Email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} required />
              <input className="input" type="password" placeholder="Password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} required />
                <input className="input" type="password" placeholder="Confirm password" value={regConfirm} onChange={(e) => setRegConfirm(e.target.value)} required />
                <button className="btn" type="submit">Register</button>
              </form>
            )}

            {recoveryStage !== "login" && (
              <PasswordRecoveryPanel
                portal="admin"
                stage={recoveryStage}
                email={email}
                otp={recoveryOtp}
                newPassword={newResetPassword}
                confirmPassword={confirmResetPassword}
                showNewPassword={showNewResetPassword}
                showConfirmPassword={showConfirmResetPassword}
                loading={recoveryLoading}
                cooldown={recoveryCooldown}
                error={recoveryError}
                message={recoveryMessage}
                onEmailChange={(value) => {
                  setEmail(value);
                  setRecoveryError("");
                }}
                onOtpChange={(value) => {
                  setRecoveryOtp(value);
                  setRecoveryError("");
                }}
                onNewPasswordChange={(value) => {
                  setNewResetPassword(value);
                  setRecoveryError("");
                }}
                onConfirmPasswordChange={(value) => {
                  setConfirmResetPassword(value);
                  setRecoveryError("");
                }}
                onToggleNewPassword={() => setShowNewResetPassword((value) => !value)}
                onToggleConfirmPassword={() => setShowConfirmResetPassword((value) => !value)}
                onSendOtp={sendPasswordResetOtp}
                onVerifyOtp={verifyPasswordResetOtp}
                onResendOtp={sendPasswordResetOtp}
                onChangePassword={changePassword}
                onBack={returnToLogin}
              />
            )}

            {recoveryStage === "login" && (
              <div className="login-secondary-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={adminLoginLoading}
                  onClick={() => {
                    setAdminLoginError("");
                    setShowRegister((value) => !value);
                  }}
                >
                  {showRegister ? "Back to login" : "Create account"}
                </button>
                {!showRegister && (
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={startPasswordRecovery}
                  >
                    Forgot password
                  </button>
                )}
              </div>
            )}

            <small className="login-footnote">
              Secure access for QueueLess business administrators.
            </small>
          </section>
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

                  {adminServices.length ? (
                    <ul className="service-list">
                      {adminServices.map((s) => (
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

      {passwordChanged && (
        <div className="password-reset-overlay">
          <section
            className="password-reset-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="password-reset-success-title"
          >
            <h2 id="password-reset-success-title">Password changed</h2>
            <p>Your password has been changed successfully! Please log in with your new password.</p>
            <button
              className="btn btn-admin-login"
              type="button"
              onClick={() => setPasswordChanged(false)}
            >
              OK
            </button>
          </section>
        </div>
      )}
    </div>
  );
}