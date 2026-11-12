export function AboutPageContent() {
  return (
    <div className="about-page">
      <header className="page-header">
        <h1>About &amp; Limitations</h1>
        <p className="subtitle">
          Architecture, privacy, supported platforms, data provenance, and
          honest known limitations.
        </p>
      </header>

      <section className="about-section">
        <h2>Architecture</h2>
        <p>
          Experience Budget is a three-layer system: a hosted website (React
          frontend + FastAPI control plane), a locally installed gateway agent,
          and a secure outbound WebSocket control channel. The cloud backend
          never executes commands on your computer; it communicates with the
          local agent, which applies policies on your hardware.
        </p>
        <pre className="arch">INTERNET → EXISTING ROUTER → EXPERIENCE BUDGET GATEWAY → MANAGED ACCESS POINT → HOUSEHOLD DEVICES</pre>
      </section>

      <section className="about-section">
        <h2>Privacy</h2>
        <ul>
          <li>No encrypted application payloads are inspected.</li>
          <li>No browsing history, URLs, or private messages are collected.</li>
          <li>Raw MAC addresses, IP addresses, and hostnames are never persisted to the cloud.</li>
          <li>Pseudonymous client identifiers are used; identity mapping stays on the gateway.</li>
          <li>You control data retention and can delete your data.</li>
        </ul>
      </section>

      <section className="about-section">
        <h2>Supported platforms</h2>
        <table>
          <thead>
            <tr><th>Platform</th><th>Enforcement</th><th>Observation</th><th>Notes</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Linux</td>
              <td>tc, CAKE, HTB+fq_codel</td>
              <td>Full per-client</td>
              <td>Recommended for enforcement</td>
            </tr>
            <tr>
              <td>OpenWrt</td>
              <td>tc, CAKE, HTB+fq_codel</td>
              <td>Full per-client</td>
              <td>Compatible Linux router</td>
            </tr>
            <tr>
              <td>Windows</td>
              <td>Not available</td>
              <td>Aggregate only</td>
              <td>Observation-only mode</td>
            </tr>
            <tr>
              <td>macOS</td>
              <td>Not available</td>
              <td>Aggregate only</td>
              <td>Observation-only mode</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="about-section">
        <h2>Data provenance</h2>
        <p>
          Every observation carries a timestamp, source, scope, environment,
          quality (measured / derived / unavailable / unknown), and freshness
          status. Simulated data is isolated to the Simulation tab and carries
          <code>environment=simulated_lab</code>. It is never merged into
          production telemetry or used to train production models without
          explicit consent.
        </p>
      </section>

      <section className="about-section">
        <h2>Known limitations</h2>
        <ul>
          <li>Full traffic enforcement requires Linux (tc/CAKE/HTB+fq_codel) or OpenWrt with root/CAP_NET_ADMIN.</li>
          <li>Windows and macOS run in observation-only mode; shaping is not claimed.</li>
          <li>Simultaneous Wi-Fi client + AP operation is hardware-dependent; a second Wi-Fi adapter or wired WAN may be required.</li>
          <li>ML models operate on real telemetry only; no accuracy figures are claimed until validated on held-out real data.</li>
          <li>Federated learning is feature-flagged and not operational.</li>
          <li>Multi-WAN failover requires more than one usable WAN interface.</li>
        </ul>
      </section>

      <section className="about-section">
        <h2>Version</h2>
        <p>Experience Budget v0.8.0 · Control plane API v1</p>
      </section>
    </div>
  );
}
