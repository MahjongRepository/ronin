export interface PageMeta {
    readonly appVersion: string;
    readonly currentYear: number;
    readonly devMode: boolean;
    readonly releaseUrl: string;
}

const CSRF_TOKEN_META = "csrf-token";

function metaElement(name: string): HTMLMetaElement | null {
    return document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
}

function metaContent(name: string): string | null {
    return metaElement(name)?.content ?? null;
}

function parseDevMode(value: string | null): boolean | null {
    if (value === "true") {
        return true;
    }
    return value === "false" ? false : null;
}

export function readPageMeta(): PageMeta | null {
    const appVersion = metaContent("ronin-app-version");
    const releaseUrl = metaContent("ronin-release-url");
    const currentYear = Number(metaContent("ronin-current-year"));
    const devMode = parseDevMode(metaContent("ronin-dev-mode"));
    if (
        !appVersion ||
        releaseUrl === null ||
        !Number.isInteger(currentYear) ||
        currentYear <= 0 ||
        devMode === null
    ) {
        return null;
    }
    return { appVersion, currentYear, devMode, releaseUrl };
}

export function readCsrfToken(): string {
    return metaContent(CSRF_TOKEN_META) ?? "";
}

export function storeCsrfToken(token: string): void {
    metaElement(CSRF_TOKEN_META)?.setAttribute("content", token);
}
