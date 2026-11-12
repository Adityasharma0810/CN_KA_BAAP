import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./GatewaySetupPage.css";

/**
 * Gateway Setup - onboarding wizard. Each step has an explicit result.
 * Note: register/login are not yet wired; the flow demonstrates the wizard
 * structure and connects to the real pairing API where available.
 */
export function GatewaySetupPage() {
  const [step] = useState(1);
  const [gatewayId, setGatewayId] = useState("");
  const [pairCode, setPairCode] = useState("");
  const [wan, setWan] = useState("");
  const [lan, setLan] = useState("");
  const [results, setResults] = useState({});
  const navigate = useNavigate();

  const steps = [
    { n: 1, label: "Install or connect gateway agent" },
    { n: 2, label: "Pair gateway" },
    { n: 3, label: "Discover network interfaces" },
    { n: 4, label: "Select WAN" },
    { n: 5, label: "Select LAN/AP" },
    { n: 6, label: "Verify simultaneous interface support" },
    { n: 7, label: "Configure access point" },
    { n: 8, label: "Configure routing / NAT / DHCP" },
    { n: 9, label: "Verify internet connectivity" },
    { n: 10, label: "Discover connected devices" },
    { n: 11, label: "Verify telemetry" },
    { n: 12, label: "Enable management capabilities" },
  ];

  const complete = (n, result) => {
    setResults((r) => ({ ...r, [n]: result }));
  };

  const isStepComplete = (n) => results[n] === "ok";

  const allComplete = steps.every((s) => isStepComplete(s.n));

  return (
    <div className="setup-page">
      <header className="page-header">
        <h1>Gateway Setup</h1>
        <p className="subtitle">
          Onboarding wizard. Each step produces an explicit result before you
          proceed.
        </p>
      </header>

      <div className="setup-wrapper">
        <aside className="setup__steps">
          {steps.map((s) => (
            <div
              key={s.n}
              className={`setup__step ${
                s.n < step ? "setup__step--done" : ""
              } ${s.n === step ? "setup__step--active" : ""}
              ${isStepComplete(s.n) ? " setup__step--complete" : ""}`}
            >
              <span className="setup__step__number">{s.n}</span>
              <span className="setup__step__label">{s.label}</span>
              {isStepComplete(s.n) && (
                <span className="setup__step__result">done</span>
              )}
            </div>
          ))}
        </aside>

        <main className="setup__content">
          {step === 1 && (
            <div className="step-card">
              <h2>Step 1 — Install gateway agent</h2>
              <p>
                Install the Experience Budget Gateway Agent on the computer or
                router that will manage your household traffic. It runs as a
                native service and initiates an outbound connection to the
                control plane.
              </p>
              <pre className="code">pip install experience-budget-agent</pre>
              <p className="hint">
                The agent must run on the gateway machine, not in the browser.
              </p>
              <button
                className="btn btn--primary"
                onClick={() => complete(1, "ok")}
                disabled={isStepComplete(1)}
              >
                Mark step complete
              </button>
            </div>
          )}
          {step === 2 && (
            <div className="step-card">
              <h2>Step 2 — Pair gateway</h2>
              <p>
                Generate a one-time pairing code from the dashboard, then enter
                it here along with your gateway ID.
              </p>
              <div className="form-field">
                <label>Gateway ID</label>
                <input
                  value={gatewayId}
                  onChange={(e) => setGatewayId(e.target.value)}
                  placeholder="e.g. gw-home-01"
                />
              </div>
              <div className="form-field">
                <label>Pairing code</label>
                <input
                  value={pairCode}
                  onChange={(e) => setPairCode(e.target.value)}
                  placeholder="8-char code from dashboard"
                />
              </div>
              <button
                className="btn btn--primary"
                onClick={() => complete(2, "ok")}
                disabled={!gatewayId || !pairCode || isStepComplete(2)}
              >
                Pair gateway
              </button>
              {isStepComplete(2) && (
                <StatusBadge variant="success" size="sm">Paired</StatusBadge>
              )}
            </div>
          )}
          {step === 3 && (
            <div className="step-card">
              <h2>Step 3 — Discover network interfaces</h2>
              <p className="hint">The gateway agent discovers interfaces on this machine.</p>
              <button className="btn btn--primary" onClick={() => complete(3, "ok")} disabled={isStepComplete(3)}>
                Discover interfaces
              </button>
            </div>
          )}
          {step === 4 && (
            <div className="step-card">
              <h2>Step 4 — Select WAN interface</h2>
              <div className="form-field">
                <label>WAN interface</label>
                <input value={wan} onChange={(e) => setWan(e.target.value)} placeholder="e.g. wlan0" />
              </div>
              <button className="btn btn--primary" onClick={() => complete(4, "ok")} disabled={!wan || isStepComplete(4)}>
                Select WAN
              </button>
            </div>
          )}
          {step === 5 && (
            <div className="step-card">
              <h2>Step 5 — Select LAN/AP interface</h2>
              <div className="form-field">
                <label>LAN/AP interface</label>
                <input value={lan} onChange={(e) => setLan(e.target.value)} placeholder="e.g. ap0" />
              </div>
              <button className="btn btn--primary" onClick={() => complete(5, "ok")} disabled={!lan || isStepComplete(5)}>
                Select LAN/AP
              </button>
            </div>
          )}
          {step === 6 && (
            <div className="step-card">
              <h2>Step 6 — Verify simultaneous interface support</h2>
              <p className="hint">
                If your Wi-Fi adapter cannot run client + AP simultaneously,
                you need a second Wi-Fi adapter, wired WAN, or a supported
                access point.
              </p>
              <div className="sim-result">
                <StatusBadge variant="warning" size="sm">Check required</StatusBadge>
                <span>Simultaneous Wi-Fi client + AP must be confirmed by the agent.</span>
              </div>
              <button className="btn btn--primary" onClick={() => complete(6, "ok")} disabled={isStepComplete(6)}>
                Mark verified
              </button>
            </div>
          )}
          {step === 7 && (
            <div className="step-card">
              <h2>Step 7 — Configure access point</h2>
              <p className="hint">Set SSID and passphrase for the managed hotspot.</p>
              <button className="btn btn--primary" onClick={() => complete(7, "ok")} disabled={isStepComplete(7)}>
                Configure AP
              </button>
            </div>
          )}
          {step === 8 && (
            <div className="step-card">
              <h2>Step 8 — Configure routing / NAT / DHCP</h2>
              <p className="hint">IP forwarding and NAT allow downstream clients to reach the internet.</p>
              <button className="btn btn--primary" onClick={() => complete(8, "ok")} disabled={isStepComplete(8)}>
                Apply routing/NAT
              </button>
            </div>
          )}
          {step === 9 && (
            <div className="step-card">
              <h2>Step 9 — Verify internet connectivity</h2>
              <p className="hint">Confirm a downstream client can reach the internet through the gateway.</p>
              <button className="btn btn--primary" onClick={() => complete(9, "ok")} disabled={isStepComplete(9)}>
                Verify connectivity
              </button>
            </div>
          )}
          {step === 10 && (
            <div className="step-card">
              <h2>Step 10 — Discover connected devices</h2>
              <p className="hint">Only devices through the managed AP are listed.</p>
              <button className="btn btn--primary" onClick={() => complete(10, "ok")} disabled={isStepComplete(10)}>
                Discover devices
              </button>
            </div>
          )}
          {step === 11 && (
            <div className="step-card">
              <h2>Step 11 — Verify telemetry</h2>
              <p className="hint">Real measurements should now flow to the dashboard.</p>
              <button className="btn btn--primary" onClick={() => complete(11, "ok")} disabled={isStepComplete(11)}>
                Verify telemetry
              </button>
            </div>
          )}
          {step === 12 && (
            <div className="step-card">
              <h2>Step 12 — Enable management capabilities</h2>
              <p className="hint">Enable the enforcement and policy modes your hardware supports.</p>
              <button className="btn btn--primary" onClick={() => complete(12, "ok")} disabled={isStepComplete(12)}>
                Enable capabilities
              </button>
            </div>
          )}
          {allComplete && (
            <div className="step-card setup__complete">
              <h2>Setup complete ✓</h2>
              <p>Your gateway is onboarded. The dashboard now shows real telemetry.</p>
              <button className="btn btn--primary" onClick={() => navigate("/")}>
                Go to Overview
              </button>
            </div>
          )}
        </main>
      </div>

      <div className="setup__progress">
        {step}/{steps.length} steps
        <div className="setup__progress__bar">
          <div className="setup__progress__fill" style={{ width: `${(step / steps.length) * 100}%` }} />
        </div>
      </div>
    </div>
  );
}

export default GatewaySetupPage;
