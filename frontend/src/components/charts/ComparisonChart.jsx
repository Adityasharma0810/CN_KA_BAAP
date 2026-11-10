import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import "./ComparisonChart.css";

// Custom tooltip component (defined outside render to avoid recreation)
function CustomTooltip({ active, payload, label, tooltipFormatter, unit }) {
  if (!active || !payload || !payload.length) return null;

  const formatter = tooltipFormatter || ((value, name) =>
    `${name}: ${value !== null && value !== undefined ? Number(value).toFixed(2) : "N/A"} ${unit}`
  );

  return (
    <div className="comparison-chart__tooltip" role="tooltip">
      <div className="comparison-chart__tooltip-time">{label}</div>
      {payload.map((entry, index) => (
        <div key={index} className="comparison-chart__tooltip-row">
          <span
            className="comparison-chart__tooltip-color"
            style={{ backgroundColor: entry.color }}
          />
          <span className="comparison-chart__tooltip-name">{entry.name}</span>
          <span className="comparison-chart__tooltip-value">
            {formatter(entry.value, entry.name)}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * ComparisonChart - Synchronized dual-series line chart for baseline vs optimized comparison
 * Uses design tokens for colors, supports missing data (null values), responsive design
 */
export function ComparisonChart({
  data = [],
  baselineKey,
  optimizedKey,
  timeKey = "time",
  baselineLabel = "Baseline",
  optimizedLabel = "Experience Budget",
  unit = "",
  height = 280,
  showLegend = true,
  showGrid = true,
  showTooltip = true,
  tooltipFormatter,
  title,
  className = "",
  "aria-label": ariaLabel,
}) {
  // Validate data
  const hasData = data.length > 0;
  const hasBaselineData = hasData && data.some(d => d[baselineKey] !== null && d[baselineKey] !== undefined);
  const hasOptimizedData = hasData && data.some(d => d[optimizedKey] !== null && d[optimizedKey] !== undefined);

  // Chart configuration using design tokens
  const chartConfig = useMemo(() => ({
    baseline: {
      stroke: "var(--chart-baseline-color)",
      strokeDasharray: "4 4",
      dotStroke: "var(--chart-baseline-color)",
    },
    optimized: {
      stroke: "var(--chart-optimized-color)",
      dotStroke: "var(--chart-optimized-color)",
    },
    grid: {
      stroke: "var(--chart-grid-color)",
    },
    axis: {
      stroke: "var(--chart-axis-color)",
    },
  }), []);

  if (!hasData) {
    return (
      <div
        className={`comparison-chart comparison-chart--empty ${className}`}
        role="img"
        aria-label={ariaLabel || `${baselineLabel} vs ${optimizedLabel} comparison chart - no data available`}
      >
        <div className="comparison-chart__empty-state">
          <svg className="comparison-chart__empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p className="comparison-chart__empty-text">No data available</p>
          <p className="comparison-chart__empty-hint">Run a comparison to see results</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`comparison-chart ${className}`}
      role="img"
      aria-label={ariaLabel || `${baselineLabel} vs ${optimizedLabel} time-series comparison`}
    >
      <div className="comparison-chart__container">
        {title && <div className="comparison-chart__title">{title}</div>}
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            {showGrid && (
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--chart-grid-color)"
                vertical={false}
              />
            )}
            <XAxis
              dataKey={timeKey}
              stroke="var(--chart-axis-color)"
              fontSize={11}
              fontFamily="var(--font-family-base)"
              tick={{ fill: "var(--chart-text-color)" }}
              axisLine={{ stroke: "var(--chart-axis-color)" }}
              tickLine={{ stroke: "var(--chart-axis-color)" }}
              minTickGap={40}
              interval="preserveStartEnd"
            />
            <YAxis
              stroke="var(--chart-axis-color)"
              fontSize={11}
              fontFamily="var(--font-family-base)"
              tick={{ fill: "var(--chart-text-color)" }}
              axisLine={{ stroke: "var(--chart-axis-color)" }}
              tickLine={{ stroke: "var(--chart-axis-color)" }}
              tickFormatter={(value) => value.toFixed(1)}
            />
            {showTooltip && <Tooltip content={<CustomTooltip tooltipFormatter={tooltipFormatter} unit={unit} />} />}
            {showLegend && (
              <Legend
                wrapperStyle={{ paddingTop: 8 }}
                formatter={(value) => value}
                iconType="line"
                layout="horizontal"
                align="center"
              />
            )}

            {/* Baseline series */}
            {hasBaselineData && (
              <Line
                type="monotone"
                dataKey={baselineKey}
                name={baselineLabel}
                stroke={chartConfig.baseline.stroke}
                strokeDasharray={chartConfig.baseline.strokeDasharray}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, strokeWidth: 2, stroke: chartConfig.baseline.dotStroke }}
                connectNulls={false}
                isAnimationActive={false}
              />
            )}

            {/* Optimized series */}
            {hasOptimizedData && (
              <Line
                type="monotone"
                dataKey={optimizedKey}
                name={optimizedLabel}
                stroke={chartConfig.optimized.stroke}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, strokeWidth: 2, stroke: chartConfig.optimized.dotStroke }}
                connectNulls={false}
                isAnimationActive={false}
              />
            )}
          </LineChart>
        </ResponsiveContainer>

        {(!hasBaselineData || !hasOptimizedData) && (
          <div className="comparison-chart__partial-notice" role="status" aria-live="polite">
            {(!hasBaselineData && !hasOptimizedData) && "No data for either series"}
            {hasBaselineData && !hasOptimizedData && `Only ${baselineLabel} data available`}
            {!hasBaselineData && hasOptimizedData && `Only ${optimizedLabel} data available`}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * MultiMetricComparisonChart - Renders multiple comparison charts in a grid
 * For displaying the 6 required comparison charts together
 */
export function MultiMetricComparisonChart({
  data = [],
  metrics = [],
  timeKey = "time",
  baselineLabel = "Baseline",
  optimizedLabel = "Experience Budget",
  height = 220,
  className = "",
}) {
  if (!data.length) {
    return (
      <div className={`comparison-chart-grid ${className}`}>
        <div className="comparison-chart__empty-state" style={{ gridColumn: "1 / -1" }}>
          <p className="comparison-chart__empty-text">No comparison data available</p>
          <p className="comparison-chart__empty-hint">Run a baseline vs optimized experiment to see charts</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`comparison-chart-grid ${className}`} role="region" aria-label="Metric comparison charts">
      {metrics.map(({ key, unit, digits = 2, label }) => (
        <ComparisonChart
          key={key}
          data={data}
          baselineKey={`${key}_baseline`}
          optimizedKey={`${key}_optimized`}
          timeKey={timeKey}
          baselineLabel={baselineLabel}
          optimizedLabel={optimizedLabel}
          unit={unit}
          title={label || key}
          height={height}
          tooltipFormatter={(value) => value !== null && value !== undefined
            ? `${Number(value).toFixed(digits)} ${unit}`
            : `N/A ${unit}`}
        />
      ))}
    </div>
  );
}