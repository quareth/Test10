interface LoadingSpinnerProps {
  message?: string;
}

export default function LoadingSpinner({ message }: LoadingSpinnerProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-8)",
        gap: "var(--space-4)",
      }}
    >
      <div className="spinner" />
      {message && (
        <p
          style={{
            margin: 0,
            color: "var(--color-neutral-500)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
}
