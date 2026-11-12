import "./StatCard.css";

/**
 * StatCard - single real measured value with honest empty/unavailable states.
 */
export function StatCard({ title, value, unit, subtitle, status = "measured" }) {
  const hasValue = value !== null && value !== undefined && value !== "";
  return (
    <article className={`stat-card stat-card--${status}`}>
      <header className="stat-card__header">
        <h3 className="stat-card__title">{title}</h3>
        {subtitle && <span className="stat-card__subtitle">{subtitle}</span>}
      </header>
      <div className="stat-card__value">
        {hasValue ? (
          <>
            {value}{unit && <span className="stat-card__unit">{unit}</span>}
          </>
        ) : (
          <span className="stat-card__placeholder">—</span>
        )}
      </div>
    </article>
  );
}
