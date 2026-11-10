import "./MetricCard.css";
import { StatusBadge } from "./StatusBadge";

/**
 * MetricCard - Reusable metric display card with baseline/optimized comparison
 * Supports improvement calculation, provenance, and various display modes
 */
export function MetricCard({
  title,
  baselineValue,
  optimizedValue,
  unit,
  digits = 2,
  lowerIsBetter = true,
  baselineLabel = "Baseline",
  optimizedLabel = "Experience Budget",
  baselineProvenance,
  optimizedProvenance,
  className = "",
  showImprovement = true,
  showProvenance = true,
}) {
  // Calculate improvement
  const hasBaseline = baselineValue !== null && baselineValue !== undefined;
  const hasOptimized = optimizedValue !== null && optimizedValue !== undefined;

  let improvement = null;
  let improvementDirection = null; // 'improvement' | 'degradation' | 'neutral'

  if (hasBaseline && hasOptimized && baselineValue !== 0) {
    const rawChange = optimizedValue - baselineValue;
    const percentChange = (rawChange / baselineValue) * 100;

    if (lowerIsBetter) {
      // For latency, jitter, loss - reduction is improvement
      improvementDirection = rawChange < 0 ? 'improvement' : (rawChange > 0 ? 'degradation' : 'neutral');
      improvement = Math.abs(percentChange);
    } else {
      // For throughput - increase is improvement
      improvementDirection = rawChange > 0 ? 'improvement' : (rawChange < 0 ? 'degradation' : 'neutral');
      improvement = Math.abs(percentChange);
    }
  }

  const formatValue = (value) => {
    if (value === null || value === undefined) return "N/A";
    if (unit === "bytes") return Number(value).toLocaleString();
    return Number(value).toFixed(digits);
  };

  return (
    <article className={`metric-card ${className}`}>
      <header className="metric-card__header">
        <h3 className="metric-card__title">{title}</h3>
      </header>

      <div className="metric-card__comparison">
        {/* Baseline column */}
        <div className="metric-card__column metric-card__column--baseline">
          <span className="metric-card__column-label">
            <StatusBadge variant="baseline" size="sm">{baselineLabel}</StatusBadge>
          </span>
          <div className="metric-card__value metric-card__value--baseline">
            {formatValue(baselineValue)} <span className="metric-card__unit">{unit}</span>
          </div>
        </div>

        {/* Optimized column */}
        <div className="metric-card__column metric-card__column--optimized">
          <span className="metric-card__column-label">
            <StatusBadge variant="optimized" size="sm">{optimizedLabel}</StatusBadge>
          </span>
          <div className="metric-card__value metric-card__value--optimized">
            {formatValue(optimizedValue)} <span className="metric-card__unit">{unit}</span>
          </div>
        </div>

        {/* Improvement column */}
        {showImprovement && hasBaseline && hasOptimized && (
          <div className={`metric-card__column metric-card__column--improvement metric-card__column--improvement--${improvementDirection || 'neutral'}`}>
            <span className="metric-card__column-label">Change</span>
            <div className="metric-card__improvement">
              {improvementDirection === 'improvement' ? (
                <>
                  <span className="metric-card__improvement-value improvement" aria-label={`Improved by ${improvement.toFixed(1)}%`}>
                    {lowerIsBetter ? "−" : "+"}{improvement.toFixed(1)}%
                  </span>
                  <span className="metric-card__improvement-label">improvement</span>
                </>
              ) : improvementDirection === 'degradation' ? (
                <>
                  <span className="metric-card__improvement-value degradation" aria-label={`Degraded by ${improvement.toFixed(1)}%`}>
                    {lowerIsBetter ? "+" : "−"}{improvement.toFixed(1)}%
                  </span>
                  <span className="metric-card__improvement-label">degradation</span>
                </>
              ) : (
                <>
                  <span className="metric-card__improvement-value neutral">0%</span>
                  <span className="metric-card__improvement-label">no change</span>
                </>
              )}
            </div>
          </div>
        )}

        {showImprovement && (!hasBaseline || !hasOptimized || baselineValue === 0) && (
          <div className="metric-card__column metric-card__column--improvement metric-card__column--improvement--neutral">
            <span className="metric-card__column-label">Change</span>
            <div className="metric-card__improvement">
              <span className="metric-card__improvement-value neutral">N/A</span>
              <span className="metric-card__improvement-label">insufficient data</span>
            </div>
          </div>
        )}
      </div>

      {showProvenance && (baselineProvenance || optimizedProvenance) && (
        <footer className="metric-card__provenance">
          {baselineProvenance && (
            <span className="metric-card__provenance-item">
              <span className="metric-card__provenance-label">Baseline:</span>
              <ProvenanceText metadata={baselineProvenance} />
            </span>
          )}
          {optimizedProvenance && (
            <span className="metric-card__provenance-item">
              <span className="metric-card__provenance-label">Optimized:</span>
              <ProvenanceText metadata={optimizedProvenance} />
            </span>
          )}
        </footer>
      )}
    </article>
  );
}

function ProvenanceText({ metadata }) {
  if (!metadata) return <span className="metric-card__provenance-text">Provenance unavailable</span>;
  return (
    <span
      className="metric-card__provenance-text"
      title={`Source: ${metadata.source}; scope: ${metadata.scope}; environment: ${metadata.environment}; quality: ${metadata.quality}`}
    >
      {metadata.source} · {metadata.scope} · {metadata.environment} · {metadata.quality}
      {metadata.stale ? " · stale" : ""}
    </span>
  );
}

/**
 * Simplified MetricCard for single value display
 */
export function SimpleMetricCard({
  title,
  value,
  unit,
  digits = 2,
  provenance,
  status,
  className = "",
}) {
  return (
    <article className={`metric-card metric-card--simple ${className}`}>
      <header className="metric-card__header">
        <h3 className="metric-card__title">{title}</h3>
        {status && <StatusBadge variant={status} size="sm">{status.toUpperCase()}</StatusBadge>}
      </header>
      <div className="metric-card__simple-value">
        {value === null || value === undefined ? (
          "N/A"
        ) : unit === "bytes" ? (
          <>
            {Number(value).toLocaleString()} <span className="metric-card__unit">{unit}</span>
          </>
        ) : (
          <>
            {Number(value).toFixed(digits)} <span className="metric-card__unit">{unit}</span>
          </>
        )}
      </div>
      {provenance && (
        <footer className="metric-card__provenance">
          <ProvenanceText metadata={provenance} />
        </footer>
      )}
    </article>
  );
}