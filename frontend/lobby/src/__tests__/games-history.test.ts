import { afterAll, afterEach, describe, expect, test, vi } from "vitest";

vi.stubEnv("TZ", "Asia/Tokyo");

const { initGamesCopyLinkButtons, showGameTimesInLocalTime } = await import("@/games-history");

function renderCard(): { button: HTMLButtonElement; status: HTMLElement } {
    document.body.innerHTML = `
        <div class="games-card-actions">
            <span class="games-copy-status" role="status"></span>
            <button class="games-copy-btn" data-replay-url="/play/history/g1" type="button"></button>
        </div>`;
    initGamesCopyLinkButtons();
    const button = document.querySelector<HTMLButtonElement>(".games-copy-btn");
    const status = document.querySelector<HTMLElement>(".games-copy-status");
    if (!button || !status) {
        throw new Error("card did not render");
    }
    return { button, status };
}

function stubClipboard(writeText: (text: string) => Promise<void>): void {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

async function copyAndWaitForNotice(button: HTMLButtonElement, status: HTMLElement): Promise<void> {
    button.click();
    await vi.waitFor(() => expect(status.textContent).toBe("Link copied"));
}

afterAll(() => {
    vi.unstubAllEnvs();
});

describe("initGamesCopyLinkButtons", () => {
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

describe("showGameTimesInLocalTime", () => {
    test("shows a UTC start time in the viewer's time zone and keeps a time without an offset as served", () => {
        document.body.innerHTML = `
            <time class="games-time" datetime="2026-10-24T03:09:00+00:00">Oct 24, 03:09 UTC</time>
            <time class="games-time" datetime="2026-10-24T03:09:00">Oct 24, 03:09 UTC</time>`;

        showGameTimesInLocalTime();

        const [utc, naive] = document.querySelectorAll("time");
        expect(utc.textContent).toMatch(/24.*12:09/);
        expect(utc.textContent).not.toContain("UTC");
        expect(naive.textContent).toBe("Oct 24, 03:09 UTC");
    });
});
