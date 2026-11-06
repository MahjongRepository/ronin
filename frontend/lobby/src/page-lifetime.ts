export interface PageLifetime {
    release: () => void;
    restore: () => void;
}

export function bindToResume(resume: () => void, minHiddenMs: number): void {
    let hiddenAt: number | null = null;
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") {
            hiddenAt = Date.now();
            return;
        }
        if (hiddenAt !== null && Date.now() - hiddenAt >= minHiddenMs) {
            resume();
        }
        hiddenAt = null;
    });
    window.addEventListener("online", resume);
}

export function bindToPageLifetime({ release, restore }: PageLifetime): void {
    window.addEventListener("pagehide", release);
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            restore();
        }
    });
}
