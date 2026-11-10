import "./StatusBadge.css";

/**
 * StatusBadge - Semantic status indicator with consistent styling
 * Uses design tokens for colors, supports multiple variants and sizes
 */
export function StatusBadge({
  children,
  variant = "unknown",
  size = "default",
  className = "",
  "aria-label": ariaLabel
}) {
  const variantClasses = {
    success: "status-badge--success",
    warning: "status-badge--warning",
    failure: "status-badge--failure",
    info: "status-badge--info",
    unknown: "status-badge--unknown",
    baseline: "status-badge--baseline",
    optimized: "status-badge--optimized",
    live: "status-badge--live",
    simulated: "status-badge--simulated",
    degraded: "status-badge--degraded",
    stale: "status-badge--stale",
    offline: "status-badge--offline",
    active: "status-badge--active",
    inactive: "status-badge--inactive",
  };

  const sizeClasses = {
    sm: "status-badge--sm",
    default: "status-badge--default",
    lg: "status-badge--lg",
  };

  const combinedClassName = [
    "status-badge",
    variantClasses[variant] || variantClasses.unknown,
    sizeClasses[size] || sizeClasses.default,
    className,
  ].filter(Boolean).join(" ");

  return (
    <span
      className={combinedClassName}
      aria-label={ariaLabel || children}
      role="status"
    >
      {children}
    </span>
  );
}

/**
 * Predefined status badges for common states
 */
export const StatusBadges = {
  Live: (props) => <StatusBadge variant="live" {...props}>LIVE</StatusBadge>,
  Simulated: (props) => <StatusBadge variant="simulated" {...props}>SIMULATED</StatusBadge>,
  Baseline: (props) => <StatusBadge variant="baseline" {...props}>BASELINE</StatusBadge>,
  ExperienceBudget: (props) => <StatusBadge variant="optimized" {...props}>EXPERIENCE BUDGET</StatusBadge>,
  Degraded: (props) => <StatusBadge variant="degraded" {...props}>DEGRADED</StatusBadge>,
  Stale: (props) => <StatusBadge variant="stale" {...props}>STALE</StatusBadge>,
  Offline: (props) => <StatusBadge variant="offline" {...props}>OFFLINE</StatusBadge>,
  ModelActive: (props) => <StatusBadge variant="success" {...props}>MODEL ACTIVE</StatusBadge>,
  ModelUnavailable: (props) => <StatusBadge variant="failure" {...props}>MODEL UNAVAILABLE</StatusBadge>,
  Online: (props) => <StatusBadge variant="success" size="sm" {...props}>Online</StatusBadge>,
  OfflineClient: (props) => <StatusBadge variant="offline" size="sm" {...props}>Offline</StatusBadge>,
  Unknown: (props) => <StatusBadge variant="unknown" size="sm" {...props}>Unknown</StatusBadge>,
};