"use client";

import { useEffect } from "react";

// Catches errors thrown by the root layout itself — the one case app/error.tsx can't handle,
// since that layout (and everything it provides, like the theme) may be what's broken. This
// needs its own <html>/<body> and can't depend on ThemeProvider or Tailwind's design tokens, so
// it's plain inline styles rather than the rest of the app's usual className-based styling.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          padding: 16,
          textAlign: "center",
          background: "#0a0a0a",
          color: "#fafafa",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <p style={{ fontSize: 14, fontWeight: 500, margin: 0 }}>Krixil AI hit an unexpected error.</p>
        <p style={{ fontSize: 12, color: "#a1a1a1", margin: 0, maxWidth: 320 }}>
          Something broke at the application level. Reloading usually fixes this.
        </p>
        <button
          type="button"
          onClick={reset}
          style={{
            marginTop: 8,
            padding: "6px 14px",
            fontSize: 13,
            fontWeight: 500,
            borderRadius: 8,
            border: "none",
            background: "#fafafa",
            color: "#0a0a0a",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
