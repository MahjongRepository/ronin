import { afterEach, assert, describe, expect, it, vi } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import { engineReplayText } from "#tests/fixtures/replays";
import { FakeStandingsLoad } from "#tests/fixtures/standings";
import { type LoadReplay, type ReplayFetch } from "@/shared/api";
import { REPLAY_VERSION } from "@/shared/protocol";
import { REPLAY_URL_WRITE_INTERVAL_MS, type ReplayLocation, mountReplayView } from "@/views/replay";

interface MountedReplay {
    readonly host: HTMLElement;
    readonly clock: ManualClock;
    readonly dispose: () => void;
    readonly written: string[];
    readonly hidePage: () => void;
    readonly signals: AbortSignal[];
    /** Answer the load waiting now. */
    readonly answer: (fetched: ReplayFetch) => Promise<void>;
}

const mounts: MountedReplay[] = [];
const LINKS = { history: "/history", lobby: "/" };

async function settle(turns = 6): Promise<void> {
    if (turns > 0) {
        await Promise.resolve();
        await settle(turns - 1);
    }
}

interface FakeLocation {
    readonly location: ReplayLocation;
    readonly written: string[];
    readonly hidePage: () => void;
}

function fakeLocation(search: string): FakeLocation {
    const written: string[] = [];
    let hideListener: (() => void) | null = null;
    return {
        hidePage: () => hideListener?.(),
        location: {
            onPageHide: (listener) => {
                hideListener = listener;
                return () => {
                    hideListener = null;
                };
            },
            replaceSearch: (next) => written.push(next),
            search,
        },
        written,
    };
}

interface FakeLoader {
    readonly loadReplay: LoadReplay;
    readonly signals: AbortSignal[];
    readonly answer: (fetched: ReplayFetch) => Promise<void>;
}

/** A loader whose every load waits until the test answers it. */
function fakeLoader(): FakeLoader {
    const signals: AbortSignal[] = [];
    const pending: ((fetched: ReplayFetch) => void)[] = [];
    return {
        async answer(fetched) {
            await settle();
            pending.shift()?.(fetched);
            await settle();
        },
        loadReplay: (_gameId, signal) => {
            signals.push(signal);
            return new Promise((resolve) => {
                pending.push(resolve);
            });
        },
        signals,
    };
}

/** Mount a replay view at `search` whose every load waits until the test answers it. */
function mountReplay(search = "?v=2", standings = new FakeStandingsLoad()): MountedReplay {
    const host = document.createElement("div");
    document.body.append(host);
    const clock = new ManualClock();
    const { hidePage, location, written } = fakeLocation(search);
    const { answer, loadReplay, signals } = fakeLoader();
    const dispose = mountReplayView(host, "g1", {
        clock,
        links: LINKS,
        loadReplay,
        location,
        startStandings: () => standings,
    });
    const mounted: MountedReplay = { answer, clock, dispose, hidePage, host, signals, written };
    mounts.push(mounted);
    return mounted;
}

async function mountLoadedReplay(
    name = "riichi",
    search = "?v=2",
    standings = new FakeStandingsLoad(),
): Promise<MountedReplay> {
    const mounted = mountReplay(search, standings);
    await mounted.answer({ ok: true, text: engineReplayText(name) });
    return mounted;
}

function rootOf(host: HTMLElement): Element {
    const root = host.querySelector(".replay-board-mode");
    if (root === null) {
        throw new Error("The replay view rendered no root");
    }
    return root;
}

function button(host: HTMLElement, selector: string): HTMLButtonElement {
    const found = host.querySelector<HTMLButtonElement>(selector);
    if (found === null) {
        throw new Error(`No ${selector}`);
    }
    return found;
}

function textOf(host: HTMLElement, selector: string): string | undefined {
    return host.querySelector(selector)?.textContent?.replaceAll(/\s+/g, " ").trim();
}

function position(host: HTMLElement): string | undefined {
    return textOf(host, ".replay-controls__round");
}

function pressKey(target: EventTarget, key: string): void {
    target.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key }));
}

/** Press `key` on the focused element and return the element focused after it. */
function pressOnFocus(host: HTMLElement, key: string): Element | null {
    pressKey(document.activeElement ?? host, key);
    return document.activeElement;
}

/** Turn the wheel over `target` and return whether the page took it, so it did not scroll. */
function wheel(target: EventTarget, deltaY: number): boolean {
    const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY });
    target.dispatchEvent(event);
    return event.defaultPrevented;
}

function element(host: HTMLElement, selector: string): HTMLElement {
    const found = host.querySelector<HTMLElement>(selector);
    if (found === null) {
        throw new Error(`No ${selector}`);
    }
    return found;
}

/** Answer 404 to each load, moving the clock to each retry's time after it, and to the last load. */
async function answerNotFound(
    answer: MountedReplay["answer"],
    clock: ManualClock,
    retries: readonly number[],
): Promise<void> {
    await answer({ ok: false, status: 404 });
    const [at, ...later] = retries;
    if (at !== undefined) {
        clock.advanceTo(at);
        await answerNotFound(answer, clock, later);
    }
}

afterEach(() => {
    vi.restoreAllMocks();
    for (const mounted of mounts.splice(0)) {
        mounted.dispose();
    }
    document.body.innerHTML = "";
});

describe("mountReplayView - moving", () => {
    it("renders the board, the position and the narration of the stop it opens on", async () => {
        const { host } = await mountLoadedReplay();

        expect(host.querySelector(".game-board")).not.toBeNull();
        expect(position(host)).toBe("East 1 Step 1/28");
        expect(textOf(host, ".replay-controls__narration")).toBe("East 1: Diana deals");
        expect(button(host, ".replay-controls__move--prev").disabled).toBe(true);
    });

    it("steps with its buttons, the right arrow key and the wheel over the board", async () => {
        const { host } = await mountLoadedReplay();

        button(host, ".replay-controls__move--next").click();
        pressKey(rootOf(host), "ArrowRight");
        expect(position(host)).toBe("East 1 Step 3/28");

        expect(wheel(element(host, ".game-board"), -100)).toBe(true);
        expect(position(host)).toBe("East 1 Step 2/28");
    });

    it("leaves the wheel to scroll beside the board and where no step goes", async () => {
        const { host } = await mountLoadedReplay();

        expect(wheel(element(host, ".replay-controls__narration"), 100)).toBe(false);
        expect(wheel(element(host, ".game-board"), -100)).toBe(false);
        expect(position(host)).toBe("East 1 Step 1/28");
    });

    it("jumps to either end, with no way on from the last step", async () => {
        const { host } = await mountLoadedReplay();

        button(host, ".replay-controls__move--last").click();
        expect(position(host)).toBe("East 1 Step 28/28");
        expect(button(host, ".replay-controls__move--next").disabled).toBe(true);

        button(host, ".replay-controls__move--first").click();
        expect(position(host)).toBe("East 1 Step 1/28");
    });

    it("takes the arrow keys only inside its own root, so of two mounts only the targeted one moves", async () => {
        const first = await mountLoadedReplay();
        const second = await mountLoadedReplay();

        pressKey(rootOf(second.host), "ArrowRight");
        pressKey(document.body, "ArrowRight");

        expect([position(first.host), position(second.host)]).toEqual([
            "East 1 Step 1/28",
            "East 1 Step 2/28",
        ]);
    });

    it("ignores the arrow keys while the user types in a field", async () => {
        const { host } = await mountLoadedReplay();
        const input = document.createElement("input");
        rootOf(host).append(input);

        pressKey(input, "ArrowRight");

        expect(position(host)).toBe("East 1 Step 1/28");
    });

    it("shows the result page the cursor stands on", async () => {
        const { host } = await mountLoadedReplay("double_ron");
        button(host, ".replay-controls__move--last").click();
        expect(textOf(host, ".round-end-result__title")).toBe("Charlie West");

        button(host, ".replay-controls__move--prev").click();
        expect(textOf(host, ".round-end-result__title")).toBe("Alice South");
    });
});

describe("mountReplayView - standings", () => {
    it("shows the standings at the game's end with a row per round and the ways back, the wheel left to scroll them", async () => {
        const { host } = await mountLoadedReplay("full_game", "?v=2&round=11&step=141");
        const links = [...host.querySelectorAll<HTMLAnchorElement>(".standings__action")];

        expect(host.querySelectorAll(".standings__round--jump")).toHaveLength(12);
        expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
            ["Lobby", LINKS.lobby],
            ["Game history", LINKS.history],
        ]);
        expect(wheel(element(host, ".standings__sheet"), -100)).toBe(false);
    });

    it("says at the game's end that the standings failed to load, and shows them once a retry lands", async () => {
        const standings = new FakeStandingsLoad("failed");
        const { host } = await mountLoadedReplay("full_game", "?v=2&round=11&step=141", standings);
        const failed = [host.querySelector(".standings"), textOf(host, ".board-notice--error")];

        standings.moveTo("ready");

        expect(failed).toEqual([
            null,
            "The final standings did not load; reload the page to try again",
        ]);
        expect([host.querySelector(".standings") !== null, textOf(host, ".board-notice")]).toEqual([
            true,
            undefined,
        ]);
    });

    it("jumps from a round's row to that round's result, its arrow keys stepping on from there", async () => {
        const { host } = await mountLoadedReplay("full_game", "?v=2&round=11&step=141");
        const [, , row] = host.querySelectorAll<HTMLButtonElement>(".standings__round--jump");
        row.focus();

        row.click();
        const shown = [position(host), textOf(host, ".round-end-result__title")];
        pressOnFocus(host, "ArrowRight");

        expect(shown).toEqual(["East 3, 2 honba Step 141/141", "Exhaustive draw"]);
        expect(position(host)).toBe("East 4, 3 honba Step 1/141");
    });
});

describe("mountReplayView - round list", () => {
    it("opens with the focus on the current round and its result", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba", "?round=1&step=4");
        const toggle = button(host, ".replay-controls__round");

        toggle.click();

        expect(toggle.getAttribute("aria-expanded")).toBe("true");
        expect(document.activeElement?.getAttribute("aria-current")).toBe("true");
        expect(textOf(host, ".round-list__row[aria-current] .round-list__summary")).toBe(
            "Ron by Charlie from Diana: 2,400 (+300 honba)",
        );
    });

    it("moves between rounds by key without stepping the replay, then opens the chosen deal", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba", "?round=1&step=4");
        button(host, ".replay-controls__round").click();

        const below = pressOnFocus(host, "ArrowDown");
        pressOnFocus(host, "ArrowRight");
        expect(position(host)).toBe("East 2, 1 honba Step 5/85");

        assert(below instanceof HTMLButtonElement);
        below.click();
        expect(host.querySelector(".round-list")).toBeNull();
        expect(position(host)).toMatch(/^East 2, 2 honba Step 1[/]/);
        expect(document.activeElement).toBe(button(host, ".replay-controls__round"));
    });

    it("closes on Escape and on a click outside it, not on one inside", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba");
        button(host, ".replay-controls__round").click();

        host.querySelector<HTMLElement>(".round-list__head")?.click();
        expect(host.querySelector(".round-list")).not.toBeNull();

        document.body.click();
        expect(host.querySelector(".round-list")).toBeNull();

        button(host, ".replay-controls__round").click();
        pressKey(document.activeElement ?? host, "Escape");
        expect(host.querySelector(".round-list")).toBeNull();
    });
});

describe("mountReplayView - address", () => {
    it("opens where the address says and keeps it on the position shown, at most once per interval", async () => {
        const { clock, host, written } = await mountLoadedReplay(
            "double_ron_on_honba",
            "?v=2&round=2&step=3",
        );
        expect(position(host)).toMatch(/^East 2, 2 honba Step 4[/]/);
        expect(written).toEqual(["?v=2&round=2&step=3&seat=1"]);

        button(host, ".replay-controls__move--next").click();
        button(host, ".replay-controls__move--next").click();
        expect(written).toHaveLength(1);

        clock.advanceTo(REPLAY_URL_WRITE_INTERVAL_MS);
        expect(written.at(-1)).toBe("?v=2&round=2&step=5&seat=1");
    });

    it("writes a waiting address as the page hides, and drops it on dispose", async () => {
        const hidden = await mountLoadedReplay();
        button(hidden.host, ".replay-controls__move--next").click();
        hidden.hidePage();
        expect(hidden.written.at(-1)).toBe("?v=2&seat=0&round=0&step=1");

        const disposed = await mountLoadedReplay();
        button(disposed.host, ".replay-controls__move--next").click();
        disposed.dispose();
        disposed.clock.advanceTo(10_000);
        expect(disposed.written).toEqual(["?v=2&seat=0&round=0&step=0"]);
    });
});

describe("mountReplayView - loading", () => {
    it("waits for a replay not saved yet and shows it once it is", async () => {
        const { answer, clock, host } = mountReplay();
        await answer({ ok: false, status: 404 });
        expect(textOf(host, ".replay-state")).toBe("Waiting for the replay to be saved…");

        clock.advanceTo(500);
        await answer({ ok: true, text: engineReplayText("riichi") });

        expect(position(host)).toBe("East 1 Step 1/28");
    });

    it("says the replay was not found once its retries are spent, with a way to try again and back", async () => {
        const { answer, clock, host, signals } = mountReplay();
        await answerNotFound(answer, clock, [500, 1500, 3500]);

        expect(textOf(host, ".replay-state__title")).toBe("Replay not found");
        expect(
            [...host.querySelectorAll(".replay-state__links a")].map((link) =>
                link.getAttribute("href"),
            ),
        ).toEqual(["/history", "/"]);

        button(host, ".replay-state__links button").click();
        expect(signals).toHaveLength(5);
        expect(textOf(host, ".replay-state")).toBe("Loading the replay…");
    });

    it("refuses a replay of another version without offering to try again", async () => {
        const { answer, host } = mountReplay();
        await answer({ ok: true, text: '{"version": "0.1"}\n{"t": 8}' });

        expect(textOf(host, ".replay-state__title")).toBe("This replay cannot be shown");
        expect(textOf(host, ".replay-state__detail")).toBe(
            'It was recorded in format "0.1", which this page cannot read.',
        );
        expect(host.querySelector(".replay-state__links button")).toBeNull();
    });

    it("says a replay holding no deal holds no round", async () => {
        const { answer, host } = mountReplay();
        await answer({ ok: true, text: JSON.stringify({ version: REPLAY_VERSION }) });

        expect(textOf(host, ".replay-state__title")).toBe("This replay holds no round");
    });

    it("labels a replay that stops before the game's end, and says where it ends at its last stop", async () => {
        const { host } = await mountLoadedReplay("truncated_mid_round");
        button(host, ".replay-controls__move--last").click();

        expect(textOf(host, ".replay-controls__incomplete--end")).toBe(
            "Incomplete The recording ends here, before the game's end",
        );
    });

    it("says a replay that throws while it is read cannot be shown, without a retry, the error on the console", async () => {
        const thrown = new Error("measure failed");
        vi.spyOn(performance, "measure").mockImplementation(() => {
            throw thrown;
        });
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});

        const { host } = await mountLoadedReplay();

        expect(textOf(host, ".replay-state__title")).toBe("This replay cannot be shown");
        expect(host.querySelector(".replay-state__links button")).toBeNull();
        expect(logged).toHaveBeenCalledWith("The replay could not be shown:", thrown);
    });

    it("clears its host on dispose and takes no key afterwards", async () => {
        const { dispose, host } = await mountLoadedReplay();
        const root = rootOf(host);

        dispose();
        pressKey(root, "ArrowRight");

        expect(host.childElementCount).toBe(0);
    });

    it("aborts the load and a waiting retry on dispose, and renders nothing from a load that settles afterwards", async () => {
        const waiting = mountReplay();
        await waiting.answer({ ok: false, status: 404 });
        waiting.dispose();
        waiting.clock.advanceTo(10_000);
        await settle();
        expect([waiting.signals.length, waiting.signals[0].aborted]).toEqual([1, true]);

        const loading = mountReplay();
        loading.dispose();
        await loading.answer({ ok: true, text: engineReplayText("riichi") });
        expect(loading.host.childElementCount).toBe(0);
    });
});
