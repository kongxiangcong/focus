// Retain the real-PDF test entry point for existing acceptance commands.
// The current scenario covers single-column jumps, focus return, and bookmarks.
process.env.FOCUS_BROWSER_URL ||= `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || '8765'}`;
await import('./current_discussion_evidence_browser.mjs');
