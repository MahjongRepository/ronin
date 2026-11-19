export interface PageLifetime {
    release: () => void;
    restore: () => void;
}

export type Unbind = () => void;

export function bindToResume(resume: () => void, minHiddenMs: number): Unbind {
    let hiddenAt: number | null = null;
    function onVisibilityChange(): void {
        if (document.visibilityState === "hidden") {
            hiddenAt = Date.now();
            return;
        }
        if (hiddenAt !== null && Date.now() - hiddenAt >= minHiddenMs) {
            resume();
        }
        hiddenAt = null;
    }
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("online", resume);
    return () => {
        document.removeEventListener("visibilitychange", onVisibilityChange);
        window.removeEventListener("online", resume);
    };
}

export function bindToPageLifetime({ release, restore }: PageLifetime): Unbind {
    function onPageShow(event: PageTransitionEvent): void {
        if (event.persisted) {
            restore();
        }
    }
    window.addEventListener("beforeunload", release);
    window.addEventListener("pagehide", release);
    window.addEventListener("pageshow", onPageShow);
    return () => {
        window.removeEventListener("beforeunload", release);
        window.removeEventListener("pagehide", release);
        window.removeEventListener("pageshow", onPageShow);
    };
}
