import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, setSession, signUp } from "../lib/apiClient";

export default function SignUp({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmationRequired, setConfirmationRequired] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await signUp(email, password);
      if (result.status === "confirmation_required") {
        setConfirmationRequired(true);
        return;
      }
      if (result.access_token && result.refresh_token) {
        await setSession({ access_token: result.access_token, refresh_token: result.refresh_token });
        onSignedIn();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign up.");
    } finally {
      setBusy(false);
    }
  }

  if (confirmationRequired) {
    return (
      <div className="auth-page">
        <h1>Check your email</h1>
        <p>We sent a confirmation link to {email}. Confirm it, then sign in below.</p>
        <Link to="/login">Go to sign in</Link>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <h1>Create your account</h1>
      <form onSubmit={handleSubmit} className="auth-form">
        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Creating account…" : "Sign up"}
        </button>
      </form>
      <p>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </div>
  );
}
