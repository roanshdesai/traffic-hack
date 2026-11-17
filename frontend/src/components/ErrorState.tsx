import { ApiError } from "../api/client";

interface Props {
  error: unknown;
  onRetry?: () => void;
}

/** Error state for failed API calls. `no_dataset` gets setup instructions. */
export function ErrorState({ error, onRetry }: Props) {
  const code = error instanceof ApiError ? error.code : "unknown";
  const message = error instanceof Error ? error.message : "Something went wrong.";

  return (
    <div className="card card--error" role="alert" data-testid="error-state">
      <p className="state-tag state-tag--error">Problem</p>
      {code === "no_dataset" ? (
        <>
          <h3 className="card__title">No dataset is loaded</h3>
          <p className="card__lead">
            The API is running but has no processed dataset. In the repository root, run{" "}
            <code>make data</code>, then restart the API.
          </p>
          <p className="card__footnote">{message}</p>
        </>
      ) : (
        <>
          <h3 className="card__title">That did not work</h3>
          <p className="card__lead">{message}</p>
        </>
      )}
      {onRetry && (
        <button type="button" className="button button--secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
