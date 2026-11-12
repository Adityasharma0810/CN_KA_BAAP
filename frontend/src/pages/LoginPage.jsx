import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";
import "./LoginPage.css";

/**
 * Login - authentication gateway to the control plane.
 */
export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ email, password });
      navigate("/");
    } catch (err) {
      setError(err.message || "Login failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login__logo">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
          </svg>
          <span className="login__brand">Experience Budget</span>
        </div>
        <h2>Sign in</h2>
        <p className="login__subtitle">Manage your household gateway.</p>
        {error && (
          <div className="login__error" role="alert">{error}</div>
        )}
        <form onSubmit={handleSubmit} className="login__form">
          <div className="form-field">
            <label>Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div className="form-field">
            <label>Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>
          <button type="submit" className="btn btn--primary btn--full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="login__footer">
          Don't have an account? <a href="/register">Register</a>
        </p>
        <p className="login__note">
          A paired gateway is required to see real telemetry. Use{" "}
          <a href="/gateway-setup">Gateway Setup</a> to onboard one.
        </p>
      </div>
    </div>
  );
}

export default LoginPage;
