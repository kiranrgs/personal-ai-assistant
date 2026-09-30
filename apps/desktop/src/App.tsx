import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { clearSession, getMe, getSession, Me } from "./lib/apiClient";
import SignUp from "./pages/SignUp";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Settings from "./pages/Settings";

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = still checking
  const navigate = useNavigate();

  useEffect(() => {
    void refreshIdentity();
  }, []);

  async function refreshIdentity() {
    const session = await getSession();
    if (!session) {
      setMe(null);
      return;
    }
    try {
      setMe(await getMe());
    } catch {
      setMe(null);
    }
  }

  async function handleSignedIn() {
    await refreshIdentity();
    navigate("/chat");
  }

  async function handleSignOut() {
    await clearSession();
    setMe(null);
    navigate("/login");
  }

  if (me === undefined) {
    return <div className="app-loading">Loading…</div>;
  }

  return (
    <Routes>
      {me ? (
        <>
          <Route path="/chat" element={<Chat me={me} onSignOut={handleSignOut} />} />
          <Route path="/settings" element={<Settings me={me} onSignOut={handleSignOut} />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </>
      ) : (
        <>
          <Route path="/login" element={<Login onSignedIn={handleSignedIn} />} />
          <Route path="/signup" element={<SignUp onSignedIn={handleSignedIn} />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </>
      )}
    </Routes>
  );
}
