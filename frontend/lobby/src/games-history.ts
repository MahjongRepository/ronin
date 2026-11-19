import { type MessageKey, t } from "@/i18n";

const COPY_STATUS_MS = 2000;

type CopyOutcome = "copied" | "failed";

const COPY_STATUS_TEXT: Readonly<Record<CopyOutcome, MessageKey>> = {
    copied: "history.copy.copied",
    failed: "history.copy.failed",
};

const clearStatusTimers = new WeakMap<HTMLElement, ReturnType<typeof setTimeout>>();

async function copyText(text: string): Promise<CopyOutcome> {
    try {
        await navigator.clipboard.writeText(text);
        return "copied";
    } catch {
        return "failed";
    }
}

function clearStatusLater(status: HTMLElement): void {
    clearTimeout(clearStatusTimers.get(status));
    const timer = setTimeout(() => {
        clearStatusTimers.delete(status);
        status.textContent = "";
        delete status.dataset.outcome;
    }, COPY_STATUS_MS);
    clearStatusTimers.set(status, timer);
}

function showCopyOutcome(btn: HTMLButtonElement, outcome: CopyOutcome): void {
    const status = btn.parentElement?.querySelector<HTMLElement>(".games-copy-status");
    if (!status) {
        return;
    }
    status.textContent = t(COPY_STATUS_TEXT[outcome]);
    status.dataset.outcome = outcome;
    clearStatusLater(status);
}

export async function copyReplayLink(event: Event): Promise<void> {
    const btn = event.currentTarget;
    if (!(btn instanceof HTMLButtonElement)) {
        return;
    }
    const { replayUrl } = btn.dataset;
    if (!replayUrl) {
        return;
    }
    showCopyOutcome(btn, await copyText(window.location.origin + replayUrl));
}
