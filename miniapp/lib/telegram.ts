/**
 * Opens a Telegram user profile by username.
 * Uses openTelegramLink inside the Mini App WebView (requires https://t.me/ URL).
 * Falls back to window.open in a browser.
 * Does nothing if username is null/empty.
 */
export function openTgProfile(username: string | null): void {
  if (!username) return;
  const url = `https://t.me/${username}`;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const WebApp = require("@twa-dev/sdk").default;
    if (WebApp?.openTelegramLink) {
      WebApp.openTelegramLink(url);
      return;
    }
  } catch {
    // not in Telegram context
  }
  window.open(url, "_blank");
}
