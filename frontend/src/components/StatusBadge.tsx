interface StatusBadgeProps {
  status: string;
}

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  pending: {
    bg: "var(--color-neutral-200)",
    text: "var(--color-neutral-700)",
  },
  running: { bg: "var(--color-secondary)", text: "var(--color-secondary-text)" },
  complete: { bg: "var(--color-accent-success-bg)", text: "var(--color-accent-success-text)" },
  failed: { bg: "var(--color-accent-error-bg)", text: "var(--color-accent-error-text)" },
};

const DEFAULT_COLORS = {
  bg: "var(--color-neutral-200)",
  text: "var(--color-neutral-700)",
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const colors = STATUS_COLORS[status] ?? DEFAULT_COLORS;

  return (
    <span
      style={{
        display: "inline-block",
        padding: "var(--space-1) var(--space-3)",
        borderRadius: "9999px",
        backgroundColor: colors.bg,
        color: colors.text,
        fontSize: "var(--font-size-sm)",
        fontWeight: 500,
        lineHeight: 1.4,
        textTransform: "capitalize",
      }}
    >
      {status}
    </span>
  );
}
