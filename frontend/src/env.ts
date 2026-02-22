const DEFAULT_LOBBY_URL = "/";

/** Lobby server URL from env.js, with localhost fallback. */
export function getLobbyUrl(): string {
    return (window as unknown as Record<string, string>).__LOBBY_URL__ || DEFAULT_LOBBY_URL;
}

declare const APP_VERSION: string;
declare const GIT_COMMIT: string;

/** App version injected at build time, falls back to "dev". */
export function getAppVersion(): string {
    return typeof APP_VERSION !== "undefined" ? APP_VERSION : "dev";
}

/** Git commit SHA injected at build time, falls back to "dev". */
export function getGitCommit(): string {
    return typeof GIT_COMMIT !== "undefined" ? GIT_COMMIT : "dev";
}
