import "./EmptyState.css";

export function EmptyState({ title, message, action, actionLabel }) {
  return (
    <div className="empty-state">
      <div className="empty-state__body">
        <h3 className="empty-state__title">{title}</h3>
        <p className="empty-state__message">{message}</p>
        {action && actionLabel && (
          <button className="btn btn--primary" onClick={action}>
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  );
}

export function LoadingState({ message = "Loading…" }) {
  return (
    <div className="loading-state">
      <span className="loading-dot" />
      <span className="loading-dot" />
      <span className="loading-dot" />
      <span className="muted">{message}</span>
    </div>
  );
}
