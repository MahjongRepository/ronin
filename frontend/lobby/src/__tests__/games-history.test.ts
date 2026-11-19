import { afterEach, describe, expect, test, vi } from "vitest";

import { copyReplayLink } from "@/games-history";

function renderCard(): { button: HTMLButtonElement; status: HTMLElement } {
    document.body.innerHTML = `
        <div class="games-card-actions">
            <span class="games-copy-status" role="status"></span>
            <button class="games-copy-btn" data-replay-url="/play/history/g1" type="button"></button>
        </div>`;
    const button = document.querySelector<HTMLButtonElement>(".games-copy-btn");
    const status = document.querySelector<HTMLElement>(".games-copy-status");
    if (!button || !status) {
        throw new Error("card did not render");
    }
    button.addEventListener("click", (event) => void copyReplayLink(event));
    return { button, status };
}

function stubClipboard(writeText: (text: string) => Promise<void>): void {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

async function copyAndWaitForNotice(button: HTMLButtonElement, status: HTMLElement): Promise<void> {
    button.click();
    await vi.waitFor(() => expect(status.textContent).toBe("Link copied"));
}

describe("copyReplayLink", () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    test("copies the absolute replay link and announces it, clearing the notice afterwards", async () => {
        vi.useFakeTimers();
        const writeText = vi.fn(async () => {});
        stubClipboard(writeText);
        const { button, status } = renderCard();

        button.click();
        await vi.waitFor(() => expect(status.textContent).toBe("Link copied"));

        expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/play/history/g1`);
        vi.runAllTimers();
        expect(status.textContent).toBe("");
    });

    test("keeps the notice of a repeated copy for its full time", async () => {
        vi.useFakeTimers();
        stubClipboard(async () => {});
        const { button, status } = renderCard();

        await copyAndWaitForNotice(button, status);
        vi.advanceTimersByTime(1500);
        status.textContent = "";
        await copyAndWaitForNotice(button, status);
        vi.advanceTimersByTime(1000);

        expect(status.textContent).toBe("Link copied");
    });

    test("announces a failure when the clipboard refuses the write", async () => {
        stubClipboard(async () => {
            throw new DOMException("denied", "NotAllowedError");
        });
        const { button, status } = renderCard();

        button.click();

        await vi.waitFor(() => expect(status.textContent).toBe("Couldn't copy"));
        expect(status.dataset.outcome).toBe("failed");
    });
});
