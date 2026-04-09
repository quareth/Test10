interface TriggerBadgeProps {
  trigger: "manual" | "scheduled";
}

const TRIGGER_STYLES: Record<
  string,
  { borderColor: string; color: string; label: string }
> = {
  manual: {
    borderColor: "var(--color-neutral-300)",
    color: "var(--color-neutral-500)",
    label: "Manual",
  },
  scheduled: {
    borderColor: "var(--color-secondary)",
    color: "var(--color-secondary-text, var(--color-neutral-600))",
    label: "Scheduled",
  },
};

export default function TriggerBadge({ trigger }: TriggerBadgeProps) {
  const style = TRIGGER_STYLES[trigger] ?? TRIGGER_STYLES.manual;

  return (
    <span
      style={{
        display: "inline-block",
        padding: "0 var(--space-2)",
        borderRadius: "9999px",
        border: `1px solid ${style.borderColor}`,
        color: style.color,
        fontSize: "var(--font-size-xs, 0.75rem)",
        fontWeight: 500,
        lineHeight: 1.8,
        whiteSpace: "nowrap",
      }}
    >
      {style.label}
    </span>
  );
}
