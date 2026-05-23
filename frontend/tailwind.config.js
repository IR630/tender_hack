/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "var(--color-paper)",
        "paper-2": "var(--color-paper-2)",
        "paper-3": "var(--color-paper-3)",
        rule: "var(--color-rule)",
        "rule-2": "var(--color-rule-2)",
        muted: "var(--color-muted)",
        neutral: "var(--color-neutral)",
        "ink-2": "var(--color-ink-2)",
        ink: "var(--color-ink)",
        accent: "var(--color-accent)",
        "accent-ink": "var(--color-accent-ink)",
        focus: "var(--color-focus)",
      },
      fontFamily: {
        display: "var(--font-display)",
        body: "var(--font-body)",
        mono: "var(--font-mono)",
      },
      borderRadius: {
        card: "var(--radius-card)",
        pill: "var(--radius-pill)",
        input: "var(--radius-input)",
      },
      letterSpacing: {
        label: "var(--tracking-label)",
        display: "var(--tracking-display)",
      },
    },
  },
  plugins: [],
};
