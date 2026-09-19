/**
 * LoginPage — Full-screen animated login for Competency Intelligence Platform.
 * Connects to POST /api/v1/auth/login, stores JWT tokens via Zustand authStore.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuthStore } from "@/store/authStore";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Backend uses JSON body LoginRequest: { email, password }
      const { data } = await axios.post(
        `${API_BASE}/api/v1/auth/token`,
        { email, password },
        { headers: { "Content-Type": "application/json" } }
      );

      setTokens(data.access_token, data.refresh_token ?? "");

      // Fetch user profile
      const { data: profile } = await axios.get(`${API_BASE}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      setUser(profile);

      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const msg =
          err.response?.data?.detail ??
          err.response?.data?.message ??
          "Login failed. Check your credentials.";
        setError(typeof msg === "string" ? msg : JSON.stringify(msg));
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      {/* Animated background blobs */}
      <div style={{ ...styles.blob, ...styles.blob1 }} />
      <div style={{ ...styles.blob, ...styles.blob2 }} />
      <div style={{ ...styles.blob, ...styles.blob3 }} />

      <div style={styles.card}>
        {/* Logo / Brand */}
        <div style={styles.brand}>
          <div style={styles.logoRing}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <h1 style={styles.brandTitle}>Competency Intelligence</h1>
            <p style={styles.brandSub}>Platform</p>
          </div>
        </div>

        <h2 style={styles.heading}>Welcome back</h2>
        <p style={styles.subheading}>Sign in to continue to your portal</p>

        {error && (
          <div style={styles.errorBox} id="login-error">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" stroke="#ff6b6b" strokeWidth="2" />
              <line x1="12" y1="8" x2="12" y2="12" stroke="#ff6b6b" strokeWidth="2" strokeLinecap="round" />
              <circle cx="12" cy="16" r="1" fill="#ff6b6b" />
            </svg>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} style={styles.form} id="login-form">
          <div style={styles.fieldGroup}>
            <label style={styles.label} htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              style={styles.input}
              onFocus={(e) => {
                e.target.style.borderColor = "#7c6cff";
                e.target.style.boxShadow = "0 0 0 3px rgba(124,108,255,0.15)";
              }}
              onBlur={(e) => {
                e.target.style.borderColor = "rgba(255,255,255,0.1)";
                e.target.style.boxShadow = "none";
              }}
            />
          </div>

          <div style={styles.fieldGroup}>
            <label style={styles.label} htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              style={styles.input}
              onFocus={(e) => {
                e.target.style.borderColor = "#7c6cff";
                e.target.style.boxShadow = "0 0 0 3px rgba(124,108,255,0.15)";
              }}
              onBlur={(e) => {
                e.target.style.borderColor = "rgba(255,255,255,0.1)";
                e.target.style.boxShadow = "none";
              }}
            />
          </div>

          <button
            type="submit"
            id="login-submit"
            disabled={loading}
            style={{
              ...styles.button,
              opacity: loading ? 0.7 : 1,
              cursor: loading ? "not-allowed" : "pointer",
            }}
            onMouseEnter={(e) => {
              if (!loading) {
                (e.target as HTMLButtonElement).style.transform = "translateY(-1px)";
                (e.target as HTMLButtonElement).style.boxShadow =
                  "0 8px 30px rgba(124,108,255,0.5)";
              }
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLButtonElement).style.transform = "none";
              (e.target as HTMLButtonElement).style.boxShadow =
                "0 4px 20px rgba(124,108,255,0.3)";
            }}
          >
            {loading ? (
              <span style={styles.spinner} />
            ) : (
              "Sign in"
            )}
          </button>
        </form>

        <div style={styles.divider}>
          <span style={styles.dividerLine} />
          <span style={styles.dividerText}>Demo credentials</span>
          <span style={styles.dividerLine} />
        </div>

        <div style={styles.demoGrid}>
          <button
            style={styles.demoChip}
            onClick={() => { setEmail("manager@company.com"); setPassword("password123"); }}
          >
            👔 Manager
          </button>
          <button
            style={styles.demoChip}
            onClick={() => { setEmail("employee@company.com"); setPassword("password123"); }}
          >
            🎓 Employee
          </button>
        </div>

        <p style={styles.footer}>
          Powered by{" "}
          <span style={{ color: "#7c6cff", fontWeight: 600 }}>NVIDIA NIM</span>{" "}
          · Meta Llama 3.1
        </p>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        @keyframes float1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(40px, -30px) scale(1.05); }
        }
        @keyframes float2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(-30px, 40px) scale(1.08); }
        }
        @keyframes float3 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(20px, 20px) scale(0.95); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f0c29, #1a1040, #16213e)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'Inter', system-ui, sans-serif",
    position: "relative",
    overflow: "hidden",
  },
  blob: {
    position: "absolute",
    borderRadius: "50%",
    filter: "blur(80px)",
    opacity: 0.35,
    pointerEvents: "none",
  },
  blob1: {
    width: 500,
    height: 500,
    background: "radial-gradient(circle, #7c6cff, #a855f7)",
    top: "-150px",
    left: "-150px",
    animation: "float1 8s ease-in-out infinite",
  },
  blob2: {
    width: 400,
    height: 400,
    background: "radial-gradient(circle, #06b6d4, #3b82f6)",
    bottom: "-100px",
    right: "-100px",
    animation: "float2 10s ease-in-out infinite",
  },
  blob3: {
    width: 300,
    height: 300,
    background: "radial-gradient(circle, #f59e0b, #ec4899)",
    top: "50%",
    left: "60%",
    animation: "float3 12s ease-in-out infinite",
  },
  card: {
    position: "relative",
    zIndex: 1,
    background: "rgba(255, 255, 255, 0.05)",
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "24px",
    padding: "48px 40px",
    width: "100%",
    maxWidth: "420px",
    boxShadow: "0 25px 80px rgba(0,0,0,0.5)",
    animation: "fadeUp 0.5s ease-out both",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "32px",
  },
  logoRing: {
    width: "48px",
    height: "48px",
    borderRadius: "14px",
    background: "linear-gradient(135deg, #7c6cff, #a855f7)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 4px 15px rgba(124,108,255,0.4)",
    flexShrink: 0,
  },
  brandTitle: {
    fontSize: "15px",
    fontWeight: 700,
    color: "#fff",
    margin: 0,
    letterSpacing: "-0.02em",
  },
  brandSub: {
    fontSize: "12px",
    color: "rgba(255,255,255,0.45)",
    margin: 0,
    marginTop: "1px",
  },
  heading: {
    fontSize: "26px",
    fontWeight: 700,
    color: "#fff",
    margin: "0 0 6px 0",
    letterSpacing: "-0.03em",
  },
  subheading: {
    fontSize: "14px",
    color: "rgba(255,255,255,0.5)",
    margin: "0 0 28px 0",
  },
  errorBox: {
    display: "flex",
    alignItems: "flex-start",
    gap: "8px",
    background: "rgba(255,107,107,0.1)",
    border: "1px solid rgba(255,107,107,0.25)",
    borderRadius: "10px",
    padding: "10px 14px",
    fontSize: "13px",
    color: "#ff9999",
    marginBottom: "20px",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "18px",
  },
  fieldGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  label: {
    fontSize: "13px",
    fontWeight: 500,
    color: "rgba(255,255,255,0.65)",
  },
  input: {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "10px",
    padding: "12px 14px",
    fontSize: "14px",
    color: "#fff",
    outline: "none",
    transition: "border-color 0.2s, box-shadow 0.2s",
    width: "100%",
    boxSizing: "border-box",
  },
  button: {
    background: "linear-gradient(135deg, #7c6cff, #a855f7)",
    color: "#fff",
    border: "none",
    borderRadius: "12px",
    padding: "14px",
    fontSize: "15px",
    fontWeight: 600,
    width: "100%",
    marginTop: "4px",
    transition: "transform 0.2s, box-shadow 0.2s, opacity 0.2s",
    boxShadow: "0 4px 20px rgba(124,108,255,0.3)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
  },
  spinner: {
    display: "inline-block",
    width: "18px",
    height: "18px",
    border: "2px solid rgba(255,255,255,0.3)",
    borderTopColor: "#fff",
    borderRadius: "50%",
    animation: "spin 0.7s linear infinite",
  },
  divider: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    margin: "24px 0 16px",
  },
  dividerLine: {
    flex: 1,
    height: "1px",
    background: "rgba(255,255,255,0.1)",
  },
  dividerText: {
    fontSize: "12px",
    color: "rgba(255,255,255,0.35)",
    whiteSpace: "nowrap",
  },
  demoGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "10px",
    marginBottom: "24px",
  },
  demoChip: {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "10px",
    padding: "10px",
    fontSize: "13px",
    color: "rgba(255,255,255,0.75)",
    cursor: "pointer",
    transition: "background 0.2s, border-color 0.2s",
    fontFamily: "inherit",
  },
  footer: {
    textAlign: "center",
    fontSize: "12px",
    color: "rgba(255,255,255,0.3)",
    margin: 0,
  },
};
