export interface PageLifetime {
    release: () => void;
    restore: () => void;
}

export function bindToPageLifetime({ release, restore }: PageLifetime): void {
    window.addEventListener("pagehide", release);
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            restore();
        }
    });
}
