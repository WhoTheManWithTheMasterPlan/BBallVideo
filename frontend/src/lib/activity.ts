/**
 * Lightweight client-side activity tracker.
 * Sends fire-and-forget events to the backend activity log.
 */
export function trackEvent(action: string, details?: Record<string, unknown>) {
  fetch("/api/v1/activity/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, details, page: window.location.pathname }),
  }).catch(() => {}); // silently ignore failures
}
