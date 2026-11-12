import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDiagnosis } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./NetworkHealthPage.css";

/**
 * Network Health & Recovery - ranked root-cause hypotheses from real evidence.
 * No automatic remediation on weak evidence; user approval required.
 */
export function NetworkHealthPage() {
  const [diagnosis, setDiagnosis] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const res = await getDiagnosis("gw-local");
        if (disposed) return;
        setDiagnosis(res);
      } catch {
        setDiagnosis(null);
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    load();
    return () => {
      disposed = true;
    };
  }, []);

  return (
    <div className="network-health-page">
      <header className="page-header">
        <h1>Network Health &amp; Recovery</h1>
        <p className="subtitle">
          Ranked root-cause hypotheses based on real evidence. No automatic
          remediation without your approval.
        </p>
      </header>

      {loading ? (
        <div className="page-empty">Analyzing…</div>
      ) : !diagnosis ? (
        <EmptyState
          title="No diagnosis available"
          message="Pair a gateway and collect telemetry to run diagnostics."
          action={() => navigate("/gateway-setup")}
          actionLabel="Set up a gateway"
        />
      ) : (
        <>
          <div className="diagnosis-summary">
            <span className="summary__label">Diagnosed</span>
            <span className="summary__time">{new Date(diagnosis.diagnosed_at).toLocaleTimeString()}</span>
            <p className="summary__text">{diagnosis.summary}</p>
          </div>
          <div className="hypotheses">
            {diagnosis.hypotheses.map((h, i) => (
              <div key={i} className="hypothesis">
                <div className="hypothesis__header">
                  <span className="hypothesis__cause">{h.cause}</span>
                  <span className="hypothesis__confidence">
                    {(h.confidence * 100).toFixed(0)}% confidence
                  </span>
                </div>
                {h.evidence && h.evidence.length > 0 && (
                  <ul className="hypothesis__evidence">
                    {h.evidence.map((e, j) => (
                      <li key={j}>{e}</li>
                    ))}
                  </ul>
                )}
                {h.recommended_fix && (
                  <div className="hypothesis__fix">
                    <strong>Recommended:</strong> {h.recommended_fix}
                  </div>
                )}
                {h.requires_approval && (
                  <div className="hypothesis__approval">
                    <StatusBadge variant="warning" size="sm">Requires approval</StatusBadge>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="remediation-note">
            <p>
              Corrective actions (channel changes, interface restarts, client
              isolation) are never applied automatically on weak evidence.
              You must approve any change that alters your network state.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

export default NetworkHealthPage;
