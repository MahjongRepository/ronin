import { afterEach, describe, expect, it } from "vitest";

import { ENGINE_REPLAYS } from "#tests/fixtures/replays";
import { type ReplayFetch } from "@/shared/api";
import { mountReplayView } from "@/views/replay";

interface MountedReplay {
    readonly host: HTMLElement;
    readonly dispose: () => void;
    readonly signal: () => AbortSignal | null;
    readonly settle: (fetched: ReplayFetch) => Promise<void>;
}

const mounts: MountedReplay[] = [];

/** Mount a replay view whose load answers when the test settles it. */
function mountReplay(): MountedReplay {
    const host = document.createElement("div");
    document.body.append(host);
    let resolve: ((fetched: ReplayFetch) => void) | null = null;
    let loadSignal: AbortSignal | null = null;
    const loaded = new Promise<ReplayFetch>((settle) => {
        resolve = settle;
    });
    const dispose = mountReplayView(host, "g1", {
        loadReplay: (_gameId, signal) => {
            loadSignal = signal;
            return loaded;
        },
    });
    const mounted: MountedReplay = {
        dispose,
        host,
        async settle(fetched) {
            resolve?.(fetched);
            await loaded;
            await Promise.resolve();
        },
        signal: () => loadSignal,
    };
    mounts.push(mounted);
    return mounted;
}

async function mountLoadedReplay(name = "riichi"): Promise<MountedReplay> {
    const mounted = mountReplay();
    const text = ENGINE_REPLAYS.get(name);
    if (text === undefined) {
        throw new Error(`No engine replay named ${name}`);
    }
    await mounted.settle({ ok: true, text });
    return mounted;
}

function rootOf(host: HTMLElement): Element {
    const root = host.querySelector(".replay-board-mode");
    if (root === null) {
        throw new Error("The replay view rendered no root");
    }
    return root;
}

function isAtFirstStep(host: HTMLElement): boolean | undefined {
    return host.querySelector<HTMLButtonElement>(".replay-state__nav-btn")?.disabled;
}

function resultTitle(host: HTMLElement): string | undefined {
    return host
        .querySelector(".round-end-result__title")
        ?.textContent?.replaceAll(/\s+/g, " ")
        .trim();
}

function pressKey(target: EventTarget, key: string): void {
    target.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key }));
}

function wheel(target: EventTarget, deltaY: number): void {
    target.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY }));
}

afterEach(() => {
    for (const mounted of mounts.splice(0)) {
        mounted.dispose();
    }
    document.body.innerHTML = "";
});

describe("mountReplayView", () => {
    it("steps the loaded replay forward with the right arrow key and back with the wheel", async () => {
        const { host } = await mountLoadedReplay();
        expect(isAtFirstStep(host)).toBe(true);

        pressKey(rootOf(host), "ArrowRight");
        expect(isAtFirstStep(host)).toBe(false);

        wheel(rootOf(host), -100);
        expect(isAtFirstStep(host)).toBe(true);
    });

    it("takes the arrow keys only inside its own root, so of two mounts only the targeted one moves", async () => {
        const first = await mountLoadedReplay();
        const second = await mountLoadedReplay();

        pressKey(rootOf(second.host), "ArrowRight");
        pressKey(document.body, "ArrowRight");

        expect([isAtFirstStep(first.host), isAtFirstStep(second.host)]).toEqual([true, false]);
    });

    it("ignores the arrow keys while the user types in a field", async () => {
        const { host } = await mountLoadedReplay();
        const input = document.createElement("input");
        rootOf(host).append(input);

        pressKey(input, "ArrowRight");

        expect(isAtFirstStep(host)).toBe(true);
    });

    it("does not step on the wheel over an open dropdown's panel", async () => {
        const { host } = await mountLoadedReplay();
        host.querySelector<HTMLButtonElement>(".dropdown-select__trigger")?.click();
        const panel = host.querySelector(".dropdown-select__panel");
        expect(panel).not.toBeNull();

        wheel(panel ?? host, 100);

        expect(isAtFirstStep(host)).toBe(true);
    });

    it("closes an open dropdown on a click outside it, not on one inside it", async () => {
        const { host } = await mountLoadedReplay();

        host.querySelector<HTMLButtonElement>(".dropdown-select__trigger")?.click();
        const panel = host.querySelector<HTMLElement>(".dropdown-select__panel");
        expect(panel).not.toBeNull();

        panel?.click();
        expect(host.querySelector(".dropdown-select__panel")).not.toBeNull();

        document.body.click();
        expect(host.querySelector(".dropdown-select__panel")).toBeNull();
    });

    it("pages a double ron's result between its winners, back to the first after a step", async () => {
        const { host } = await mountLoadedReplay("double_ron");
        for (let step = 0; step < 200 && resultTitle(host) === undefined; step += 1) {
            pressKey(rootOf(host), "ArrowRight");
        }
        expect(resultTitle(host)).toBe("Alice South");

        host.querySelectorAll<HTMLButtonElement>(".round-end-result__page-btn")[1]?.click();
        expect(resultTitle(host)).toBe("Charlie West");

        pressKey(rootOf(host), "ArrowLeft");
        pressKey(rootOf(host), "ArrowRight");
        expect(resultTitle(host)).toBe("Alice South");
    });

    it("says the replay was not found when its source answers 404", async () => {
        const { host, settle } = mountReplay();
        await settle({ ok: false, status: 404 });

        expect(host.textContent?.trim()).toBe("Replay not found");
    });

    it("clears its host on dispose and takes no key afterwards", async () => {
        const { dispose, host } = await mountLoadedReplay();
        const root = rootOf(host);

        dispose();
        pressKey(root, "ArrowRight");

        expect(host.childElementCount).toBe(0);
    });

    it("aborts the load on dispose and renders nothing from a load that settles afterwards", async () => {
        const { dispose, host, settle, signal } = mountReplay();
        dispose();
        await settle({ ok: true, text: ENGINE_REPLAYS.get("riichi") ?? "" });

        expect(signal()?.aborted).toBe(true);
        expect(host.childElementCount).toBe(0);
    });
});
