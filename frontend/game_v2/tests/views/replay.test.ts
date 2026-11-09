import { afterEach, assert, describe, expect, it, vi } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import { fakeLanguageSwitch, resetPageLanguage } from "#tests/fixtures/language";
import { encodeReplayLines } from "#tests/fixtures/replay-records";
import { engineReplayBytes } from "#tests/fixtures/replays";
import { type GameSound, type SoundCue, type SoundSetting } from "@/entities/client";
import {
    DEFAULT_REPLAY_PREFS,
    HOLD_DELAY_MS,
    HOLD_REPEAT_MS,
    type ReplayPrefs,
    type ReplayPrefsStore,
} from "@/entities/replay";
import { type LoadReplay, type ReplayFetch } from "@/shared/api";
import { type Locale } from "@/shared/i18n";
import { REPLAY_VERSION, WIRE_KEY } from "@/shared/protocol";
import {
    REPLAY_URL_WRITE_INTERVAL_MS,
    type ReplayLinks,
    type ReplayLocation,
    mountReplayView,
} from "@/views/replay";

interface MountedReplay {
    readonly host: HTMLElement;
    readonly clock: ManualClock;
    readonly dispose: () => void;
    readonly written: string[];
    readonly hidePage: () => void;
    /** Make every later address write throw, as a browser refusing a history write would. */
    readonly failWrites: () => void;
    /** Make every later settings read throw `error`. */
    readonly failPrefsLoad: (error: Error) => void;
    readonly signals: AbortSignal[];
    /** Every settings write, the last one what the reader keeps. */
    readonly savedPrefs: ReplayPrefs[];
    /** Answer the load waiting now. */
    readonly answer: (fetched: ReplayFetch) => Promise<void>;
    /** Every sound played, in order, and the sound setting as this browser would keep it. */
    readonly sound: { readonly played: SoundCue[]; setting: SoundSetting };
}

const mounts: MountedReplay[] = [];
const LINKS = { history: "/history", lobby: "/" };

/**
 * The page's links, which each draw of the board reads for the game end's panel: counting those reads, throwing on
 * the next few.
 */
function drawnLinks(): {
    readonly links: ReplayLinks;
    readonly reads: { count: number; throwing: number };
} {
    const reads = { count: 0, throwing: 0 };
    return {
        links: {
            history: LINKS.history,
            get lobby(): string {
                reads.count += 1;
                if (reads.throwing > 0) {
                    reads.throwing -= 1;
                    throw new Error("the board failed to draw");
                }
                return LINKS.lobby;
            },
        },
        reads,
    };
}

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
    readonly failWrites: () => void;
}

function fakeLocation(search: string): FakeLocation {
    const written: string[] = [];
    let hideListener: (() => void) | null = null;
    const writes = { failing: false };
    return {
        failWrites: () => {
            writes.failing = true;
        },
        hidePage: () => hideListener?.(),
        location: {
            onPageHide: (listener) => {
                hideListener = listener;
                return () => {
                    hideListener = null;
                };
            },
            replaceSearch: (next) => {
                if (writes.failing) {
                    throw new Error("the history write was refused");
                }
                written.push(next);
            },
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

/** A settings store holding `prefs`, recording every write, whose reads throw once `failPrefsLoad` is called. */
function fakePrefsStore(prefs: ReplayPrefs): {
    readonly store: ReplayPrefsStore;
    readonly savedPrefs: ReplayPrefs[];
    readonly failPrefsLoad: (error: Error) => void;
} {
    const savedPrefs: ReplayPrefs[] = [];
    let loadError: Error | null = null;
    const store: ReplayPrefsStore = {
        load: () => {
            if (loadError !== null) {
                throw loadError;
            }
            return prefs;
        },
        save: (saved) => savedPrefs.push(saved),
    };
    return {
        failPrefsLoad: (error) => {
            loadError = error;
        },
        savedPrefs,
        store,
    };
}

/** The game's sounds, on or off, recording every cue played and every setting kept. */
function fakeSound(soundOn: boolean): {
    readonly sound: MountedReplay["sound"];
    readonly deps: GameSound;
} {
    const sound: MountedReplay["sound"] = { played: [], setting: { sound_on: soundOn } };
    const deps: GameSound = {
        play: (cue) => sound.played.push(cue),
        setting: {
            load: () => sound.setting,
            save: (setting) => {
                sound.setting = setting;
            },
        },
    };
    return { deps, sound };
}

interface MountOptions {
    readonly links?: ReplayLinks;
    readonly prefs?: ReplayPrefs;
    readonly soundOn?: boolean;
    readonly setLanguage?: (locale: Locale) => void;
}

/** Mount a replay view at `search` whose every load waits until the test answers it. */
function mountReplay(
    search = "",
    {
        links = LINKS,
        prefs = DEFAULT_REPLAY_PREFS,
        setLanguage = () => {},
        soundOn = false,
    }: MountOptions = {},
): MountedReplay {
    const host = document.body.appendChild(document.createElement("div"));
    const clock = new ManualClock();
    const { failPrefsLoad, savedPrefs, store } = fakePrefsStore(prefs);
    const { failWrites, hidePage, location, written } = fakeLocation(search);
    const { answer, loadReplay, signals } = fakeLoader();
    const { deps, sound } = fakeSound(soundOn);
    const dispose = mountReplayView(host, "g1", {
        clock: steadyClockOn(clock),
        links,
        loadReplay,
        location,
        prefs: store,
        setLanguage,
        sound: deps,
    });
    const mounted: MountedReplay = {
        answer,
        clock,
        dispose,
        failPrefsLoad,
        failWrites,
        hidePage,
        host,
        savedPrefs,
        signals,
        sound,
        written,
    };
    mounts.push(mounted);
    return mounted;
}

async function mountLoadedReplay(
    name = "riichi",
    search = "",
    options: MountOptions = {},
): Promise<MountedReplay> {
    const mounted = mountReplay(search, options);
    await mounted.answer({ content: engineReplayBytes(name), ok: true });
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
    return textOf(host, ".replay-status__position");
}

/** Press `key` on `target` and say whether the page prevented its default. */
function pressKey(target: EventTarget, key: string, init: KeyboardEventInit = {}): boolean {
    return !target.dispatchEvent(
        new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key, ...init }),
    );
}

/** Release `key` on `target` and say whether the page prevented its default. */
function releaseKey(target: EventTarget, key: string, init: KeyboardEventInit = {}): boolean {
    return !target.dispatchEvent(
        new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key, ...init }),
    );
}

const SPACE: KeyboardEventInit = { code: "Space" };

/** Fire the earliest live timer, and say whether there was one. */
function fireNextTimer(clock: ManualClock): boolean {
    const live = clock.timers.filter((timer) => !timer.cancelled);
    if (live.length === 0) {
        return false;
    }
    clock.advanceTo(Math.min(...live.map((timer) => timer.at)));
    return true;
}

/** Fire timers until none is left, at most `limit`, and return how many fired. */
function runTimers(clock: ManualClock, limit = 50): number {
    let fired = 0;
    while (fired < limit && fireNextTimer(clock)) {
        fired += 1;
    }
    return fired;
}

/** Run each action in turn and return the position shown after each. */
function positionsAfter(
    host: HTMLElement,
    actions: readonly (() => void)[],
): (string | undefined)[] {
    return actions.map((action) => {
        action();
        return position(host);
    });
}

function playing(host: HTMLElement): boolean {
    return button(host, ".replay-controls__play").getAttribute("aria-pressed") === "true";
}

function pointer(type: string, init: PointerEventInit = {}): PointerEvent {
    return new PointerEvent(type, {
        bubbles: true,
        button: 0,
        buttons: 1,
        detail: 1,
        isPrimary: true,
        pointerId: 1,
        ...init,
    });
}

/** Click with a count of `detail`: 0 for a keyboard's or an assistive technology's click, 1 for a pointer's. */
function click(target: EventTarget, detail: number): void {
    target.dispatchEvent(new MouseEvent("click", { bubbles: true, detail }));
}

/** Press `key` on the focused element and return the element focused after it. */
function pressOnFocus(host: HTMLElement, key: string): Element | null {
    pressKey(document.activeElement ?? host, key);
    return document.activeElement;
}

/** Give `target` the layout of a box that scrolls: `scroll` pixels of content in `client` pixels shown. */
function overflow(
    target: HTMLElement,
    { client, scroll }: { client: number; scroll: number },
): void {
    target.style.overflowY = "auto";
    Object.defineProperty(target, "scrollHeight", { value: scroll });
    Object.defineProperty(target, "clientHeight", { value: client });
}

/** Turn the wheel over `target` and return whether the page took it, so it did not scroll. */
function wheel(target: EventTarget, deltaY: number): boolean {
    const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY });
    target.dispatchEvent(event);
    return event.defaultPrevented;
}

/** A seat's hand on the board as its tile count and how many of them are backs. */
function handTiles(host: HTMLElement, seat: string): [number, number] {
    return [
        host.querySelectorAll(`.board-area--${seat}-hand .tile`).length,
        host.querySelectorAll(`.board-area--${seat}-hand .tile-back`).length,
    ];
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
    resetPageLanguage();
    for (const mounted of mounts.splice(0)) {
        mounted.dispose();
    }
    document.body.innerHTML = "";
});

describe("mountReplayView - moving", () => {
    it("renders the board and the position of the stop it opens on", async () => {
        const { host } = await mountLoadedReplay();

        expect(host.querySelector(".game-board")).not.toBeNull();
        expect(host.querySelector(".replay-rotate a")?.getAttribute("href")).toBe(LINKS.history);
        expect(position(host)).toBe("East 1 Step 1 of 28");
        expect(button(host, ".replay-controls__move--prev").disabled).toBe(true);
    });

    it("steps with its buttons, the right arrow key and the wheel over the board", async () => {
        const { host } = await mountLoadedReplay();

        button(host, ".replay-controls__move--next").click();
        pressKey(rootOf(host), "ArrowRight");
        expect(position(host)).toBe("East 1 Step 3 of 28");

        expect(wheel(element(host, ".game-board"), -100)).toBe(true);
        expect(position(host)).toBe("East 1 Step 2 of 28");
    });

    it("leaves the wheel to the status's place and to where no step goes", async () => {
        const { host } = await mountLoadedReplay();

        expect(wheel(element(host, ".replay-status"), 100)).toBe(false);
        expect(wheel(element(host, ".game-board"), -100)).toBe(false);
        expect(position(host)).toBe("East 1 Step 1 of 28");
    });

    it("jumps to either end, with no way on from the last step", async () => {
        const { host } = await mountLoadedReplay();

        button(host, ".replay-controls__move--last").click();
        expect(position(host)).toBe("East 1 Step 28 of 28");
        expect(button(host, ".replay-controls__move--next").disabled).toBe(true);

        button(host, ".replay-controls__move--first").click();
        expect(position(host)).toBe("East 1 Step 1 of 28");
    });

    it("takes the arrow keys only inside its own root, so of two mounts only the targeted one moves", async () => {
        const first = await mountLoadedReplay();
        const second = await mountLoadedReplay();

        pressKey(rootOf(second.host), "ArrowRight");
        pressKey(document.body, "ArrowRight");

        expect([position(first.host), position(second.host)]).toEqual([
            "East 1 Step 1 of 28",
            "East 1 Step 2 of 28",
        ]);
    });

    it("shows the result page the cursor stands on", async () => {
        const { host } = await mountLoadedReplay("double_ron");
        button(host, ".replay-controls__move--last").click();
        expect(textOf(host, ".round-end-result__winner")).toBe("Charlie");

        button(host, ".replay-controls__move--prev").click();
        expect(textOf(host, ".round-end-result__winner")).toBe("Alice");
    });
});

describe("mountReplayView - keys", () => {
    it("ignores keys typed into a field, composed by an input method or held with a modifier", async () => {
        const { host } = await mountLoadedReplay();
        const input = document.createElement("input");
        rootOf(host).append(input);

        pressKey(input, "ArrowRight");
        pressKey(rootOf(host), "ArrowRight", { isComposing: true });
        pressKey(rootOf(host), "Process", { code: "ArrowRight" });
        pressKey(rootOf(host), "ArrowRight", { ctrlKey: true });
        pressKey(rootOf(host), "End", { metaKey: true });

        expect(position(host)).toBe("East 1 Step 1 of 28");
    });

    it("leaves Space to a focused button, which activates itself, and takes it as autoplay's switch elsewhere", async () => {
        const { host } = await mountLoadedReplay();
        const hands = button(host, ".replay-controls__option--hands");
        hands.focus();

        pressKey(hands, " ", SPACE);
        const onButton = [position(host), playing(host)];
        pressKey(rootOf(host), " ", SPACE);

        expect(onButton).toEqual(["East 1 Step 1 of 28", false]);
        expect(playing(host)).toBe(true);
    });

    it("takes a held Enter on Next as a held step, pausing at each page of a double ron's result", async () => {
        const { host } = await mountLoadedReplay("double_ron", "?round=0&step=9");
        const next = button(host, ".replay-controls__move--next");
        next.focus();

        const prevented = [false, true, true].map((repeat) => pressKey(next, "Enter", { repeat }));
        const held = [position(host), textOf(host, ".round-end-result__winner")];
        pressKey(next, "Enter");

        expect(prevented).toEqual([true, true, true]);
        expect(held).toEqual(["East 1 Step 11 of 11", "Alice"]);
        expect(textOf(host, ".round-end-result__winner")).toBe("Charlie");
    });

    it("steps once for Space on a focused step button and once for an assistive technology's click", async () => {
        const { host } = await mountLoadedReplay();
        const next = button(host, ".replay-controls__move--next");
        next.focus();

        const prevented = [pressKey(next, " ", SPACE), releaseKey(next, " ", SPACE)];
        const afterSpace = [position(host), playing(host)];
        click(next, 0);

        expect(prevented).toEqual([true, true]);
        expect(afterSpace).toEqual(["East 1 Step 2 of 28", false]);
        expect(position(host)).toBe("East 1 Step 3 of 28");
    });
});

describe("mountReplayView - autoplay", () => {
    it("arms its timer to autoplay's next move and steps when it fires", async () => {
        const { clock, host } = await mountLoadedReplay();
        button(host, ".replay-controls__play").click();

        clock.advanceTo(clock.lastTimer().at);

        expect([position(host), playing(host)]).toEqual(["East 1 Step 2 of 28", true]);
    });

    it("goes on at its pace after the wall clock steps back an hour", async () => {
        const { clock, host } = await mountLoadedReplay();
        button(host, ".replay-controls__play").click();
        const firstDue = clock.lastTimer().at;
        clock.stepWall(-3_600_000);

        expect(
            positionsAfter(host, [
                () => clock.advanceTo(firstDue),
                () => clock.advanceTo(firstDue + 20_000),
            ]),
        ).toEqual(["East 1 Step 2 of 28", "East 1 Step 3 of 28"]);
    });

    it.each([
        ["elapsed time ran through it", (clock: ManualClock) => clock.advanceTo(60_000)],
        [
            "elapsed time paused, as a forward wall step looks",
            (clock: ManualClock) => clock.stepWall(60_000),
        ],
    ])(
        "moves one step on waking from a sleep, then goes on at its pace (%s)",
        async (_sleep, sleep) => {
            const { clock, host } = await mountLoadedReplay();
            button(host, ".replay-controls__play").click();
            const firstDue = clock.lastTimer().at;

            expect(
                positionsAfter(host, [
                    () => {
                        sleep(clock);
                        clock.advanceTo(Math.max(clock.elapsedNow(), firstDue));
                    },
                    () => clock.advanceTo(clock.elapsedNow() + 20_000),
                ]),
            ).toEqual(["East 1 Step 2 of 28", "East 1 Step 3 of 28"]);
        },
    );

    it("stops when the page hides, and cancels its timer on dispose", async () => {
        const { clock, dispose, hidePage, host } = await mountLoadedReplay();
        button(host, ".replay-controls__play").click();
        hidePage();
        runTimers(clock);
        const hidden = [playing(host), position(host)];

        button(host, ".replay-controls__play").click();
        dispose();

        expect(hidden).toEqual([false, "East 1 Step 1 of 28"]);
        expect(clock.timers.filter((timer) => !timer.cancelled)).toEqual([]);
    });

    it("says the replay cannot be shown when the address it writes as the page hides throws, autoplay stopped", async () => {
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});
        const { clock, failWrites, hidePage, host } = await mountLoadedReplay(
            "riichi",
            "?round=0&step=2",
        );
        button(host, ".replay-controls__play").click();
        clock.advanceTo(clock.lastTimer().at);
        failWrites();

        hidePage();

        expect(textOf(host, ".replay-state__title")).toBe("This replay cannot be shown");
        expect(logged).toHaveBeenCalledOnce();
        expect(clock.timers.filter((timer) => !timer.cancelled)).toEqual([]);
    });

    it("shows a bare notice with the ways back when even the cannot-be-shown screen throws, its timers stopped", async () => {
        const { links, reads } = drawnLinks();
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});
        const { clock, hidePage, host } = await mountLoadedReplay("riichi", "?round=0&step=0", {
            links,
        });
        button(host, ".replay-controls__play").click();
        reads.throwing = 2;

        clock.advanceTo(clock.lastTimer().at);
        hidePage();

        expect([
            textOf(host, ".replay-state--broken"),
            [...host.querySelectorAll(".replay-state__links a")].map((link) =>
                link.getAttribute("href"),
            ),
        ]).toEqual(["The replay page ran into an error. Game history Lobby", ["/history", "/"]]);
        expect(logged).toHaveBeenLastCalledWith(
            "The failed replay page could not be drawn:",
            expect.any(Error),
        );
        expect(clock.timers.filter((timer) => !timer.cancelled)).toEqual([]);
    });
});

describe("mountReplayView - wheel and hold", () => {
    it("leaves the wheel and the round keys to a round's result scrolling in its panel", async () => {
        const { host } = await mountLoadedReplay("double_ron", "?round=0&step=10");
        const foot = element(host, ".round-end-result__foot");
        overflow(foot, { client: 60, scroll: 200 });
        const score = element(host, ".round-end-result__score");
        const inFoot = [
            wheel(score, 100),
            ...["PageDown", "ArrowDown", "Home", "End"].map((key) => pressKey(score, key)),
        ];
        overflow(element(host, ".board-overlay__panel"), { client: 300, scroll: 600 });
        const pager = button(host, "[aria-label='Next winner']");

        const inPanel = [wheel(element(host, ".round-end-result"), -100), pressKey(pager, "Home")];

        expect([inFoot, inPanel]).toEqual([
            [false, false, false, false, false],
            [false, false],
        ]);
        expect(position(host)).toBe("East 1 Step 11 of 11");
    });

    it("steps once for a trackpad's small ticks until they add up, drawing nothing until then", async () => {
        const { links, reads } = drawnLinks();
        const { host } = await mountLoadedReplay("riichi", "?round=0&step=0", { links });
        const board = element(host, ".game-board");
        reads.count = 0;

        const taken = [wheel(board, 12), wheel(board, 12)];
        const before = [position(host), reads.count];
        wheel(board, 12);

        expect([taken, before]).toEqual([
            [true, true],
            ["East 1 Step 1 of 28", 0],
        ]);
        expect([position(host), reads.count]).toEqual(["East 1 Step 2 of 28", 1]);
    });

    it("repeats a held step button on its timer, dropping the click its press ends in", async () => {
        const { clock, host } = await mountLoadedReplay("double_ron_on_honba", "?round=0&step=136");
        const next = button(host, ".replay-controls__move--next");

        next.dispatchEvent(pointer("pointerdown"));
        next.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1 }));

        expect(
            positionsAfter(
                host,
                [HOLD_DELAY_MS - 1, HOLD_DELAY_MS].map((at) => () => clock.advanceTo(at)),
            ),
        ).toEqual(["East 1 Step 138 of 141", "East 1 Step 139 of 141"]);
    });

    it("ends a hold when the press ends, dropping only the click that press ends in", async () => {
        const { clock, host } = await mountLoadedReplay();
        const next = button(host, ".replay-controls__move--next");
        const capture = vi.spyOn(next, "setPointerCapture");

        const shown = positionsAfter(host, [
            () => {
                next.dispatchEvent(pointer("pointerdown"));
                next.dispatchEvent(pointer("pointerup"));
                click(next, 1);
                clock.advanceTo(10_000);
            },
            () => click(next, 0),
        ]);

        expect(shown).toEqual(["East 1 Step 2 of 28", "East 1 Step 3 of 28"]);
        expect(capture).not.toHaveBeenCalled();
    });

    it("pauses a hold while the pointer is off the button and goes on when it comes back still pressed", async () => {
        const { clock, host } = await mountLoadedReplay();
        const next = button(host, ".replay-controls__move--next");
        vi.spyOn(next, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 40, 40));

        next.dispatchEvent(pointer("pointerdown"));

        expect(
            positionsAfter(
                host,
                (
                    [
                        [{ clientX: 200 }, 5000],
                        [{ clientX: 20 }, 5000 + HOLD_REPEAT_MS],
                        [{ buttons: 0, clientX: 20 }, 10_000],
                    ] satisfies [PointerEventInit, number][]
                ).map(([init, at]) => () => {
                    next.dispatchEvent(pointer("pointermove", { clientY: 20, ...init }));
                    clock.advanceTo(at);
                }),
            ),
        ).toEqual(["East 1 Step 2 of 28", "East 1 Step 3 of 28", "East 1 Step 3 of 28"]);
    });
});

describe("mountReplayView - view", () => {
    it("draws the seat whose plate or centre score is pressed at the bottom and writes it into the address", async () => {
        const { clock, host, written } = await mountLoadedReplay("double_ron", "?round=0&step=10");
        const right = textOf(host, ".nameplate--right .nameplate__name");

        button(host, ".nameplate--right").click();
        const afterPlate = textOf(host, ".board-local .nameplate__name");
        host.querySelector<HTMLElement>(
            ".board-center__seat--top .board-center__score-line",
        )?.click();
        clock.advanceTo(REPLAY_URL_WRITE_INTERVAL_MS);

        expect(afterPlate).toBe(right);
        expect(written.at(-1)).toBe("?round=0&step=10&seat=3");
    });

    it("hides the other hands, and keeps the choice in the reader's settings", async () => {
        const { host, savedPrefs } = await mountLoadedReplay("riichi", "?round=0&step=2");
        const shownBacks = host.querySelectorAll(".board-strip .tile-back").length;

        button(host, ".replay-controls__option--hands").click();

        expect(shownBacks).toBe(0);
        expect(host.querySelectorAll(".board-strip .tile-back").length).toBeGreaterThan(0);
        expect(savedPrefs).toEqual([{ hideHands: true }]);
    });
    it("holds a deep link on the seating while the sound is on, the wheel moving nothing, then plays a step on's sounds until the reader turns them off from the cog", async () => {
        const { host, sound } = await mountLoadedReplay("riichi", "?round=0&step=10", {
            soundOn: true,
        });
        const held = [
            wheel(element(host, ".game-board"), 100),
            position(host),
            document.activeElement === button(host, ".seating__action"),
        ];

        button(host, ".seating__action").click();
        button(host, ".replay-controls__move--next").click();
        button(host, ".game-menu__toggle").click();
        const statusRows = host.querySelectorAll(".game-menu__status-row").length;
        button(host, ".game-menu__sound").click();
        button(host, ".replay-controls__move--next").click();

        expect(held).toEqual([false, "East 1 Step 11 of 28", true]);
        expect([sound.played, sound.setting, statusRows]).toEqual([
            ["discard", "riichi"],
            { sound_on: false },
            0,
        ]);
    });

    it("switches the page to Russian in place from the cog, its menu open, the position and address kept", async () => {
        const languages = fakeLanguageSwitch();
        const { host, written } = await mountLoadedReplay("riichi", "?round=0&step=10", {
            setLanguage: languages.setLanguage,
        });
        const shown = position(host);

        button(host, ".game-menu__toggle").click();
        button(host, '.game-menu__language-option[lang="ru"]').click();

        expect([
            shown,
            languages.chosen,
            position(host),
            host.querySelector(".game-menu__panel") !== null,
            written,
        ]).toEqual([
            "East 1 Step 11 of 28",
            ["ru"],
            "Восток 1 Шаг 11 из 28",
            true,
            ["?round=0&step=10&seat=0"],
        ]);
    });

    it("shows the hands a round's result reveals face up while the other hands hide", async () => {
        const { host } = await mountLoadedReplay("double_ron", "?round=0&step=10", {
            prefs: { hideHands: true },
        });
        expect(textOf(host, ".round-end-result__winner")).toBe("Alice");
        expect(["right", "top", "left"].map((seat) => handTiles(host, seat))).toEqual([
            [13, 0],
            [13, 0],
            [13, 13],
        ]);
    });
});

describe("mountReplayView - focus", () => {
    it("takes the focus back to its root when the control holding it can no longer act, so its keys go on", async () => {
        const { host } = await mountLoadedReplay("double_ron", "?round=0&step=10");
        const nextWinner = button(host, "[aria-label='Next winner']");
        nextWinner.focus();

        nextWinner.click();
        const focused = document.activeElement;
        pressOnFocus(host, "ArrowLeft");

        expect(focused).toBe(rootOf(host));
        expect(textOf(host, ".round-end-result__winner")).toBe("Alice");
    });
});

describe("mountReplayView - seating and game end", () => {
    it("opens on the seating at the starting scores, its start focused, when the address names no position; Start shows the board", async () => {
        const { host } = await mountLoadedReplay("riichi", "");
        const start = button(host, ".seating__action");
        const names = [...host.querySelectorAll(".seating__name")].map((name) => name.textContent);
        const scores = [...host.querySelectorAll(".seating__score")].map(
            (score) => score.textContent,
        );

        start.click();

        expect([document.activeElement === start, names.length]).toEqual([false, 4]);
        expect(scores).toEqual(["25,000", "25,000", "25,000", "25,000"]);
        expect(host.querySelector(".seating__seat--viewer")).toBeNull();
        expect([host.querySelector(".seating"), document.activeElement]).toEqual([
            null,
            rootOf(host),
        ]);
    });

    it("closes the seating on the first step, and with the sound off never opens it where the address names a position", async () => {
        const { host } = await mountLoadedReplay("riichi", "");
        pressKey(rootOf(host), "ArrowRight");
        const deepLinked = await mountLoadedReplay("riichi", "?round=0&step=0");

        expect([position(host), host.querySelector(".seating")]).toEqual([
            "East 1 Step 2 of 28",
            null,
        ]);
        expect(deepLinked.host.querySelector(".seating")).toBeNull();
    });

    it("shows the final scores at the game's end with the ways back", async () => {
        const { host } = await mountLoadedReplay("full_game", "?round=11&step=141");
        const links = [...host.querySelectorAll<HTMLAnchorElement>(".seating__action")];
        const placements = [...host.querySelectorAll(".seating__placement")].map(
            (placement) => placement.textContent,
        );

        expect(placements).toEqual(["1st", "2nd", "3rd", "4th"]);
        expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
            ["Lobby", LINKS.lobby],
            ["Game history", LINKS.history],
        ]);
    });
});

describe("mountReplayView - round list", () => {
    it("opens with the focus on the current round and its result", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba", "?round=1&step=4");
        const toggle = button(host, ".replay-controls__option--rounds");

        toggle.click();

        expect(toggle.getAttribute("aria-expanded")).toBe("true");
        expect(document.activeElement?.getAttribute("aria-current")).toBe("true");
        expect(textOf(host, ".round-list__row[aria-current] .round-list__summary")).toBe(
            "Ron by Charlie from Diana: 2,400 (+300 honba)",
        );
    });

    it("moves between rounds by key without stepping the replay, then opens the chosen deal", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba", "?round=1&step=4");
        button(host, ".replay-controls__option--rounds").click();

        const below = pressOnFocus(host, "ArrowDown");
        pressOnFocus(host, "ArrowRight");
        expect(position(host)).toBe("East 2, 1 honba Step 5 of 85");

        assert(below instanceof HTMLButtonElement);
        below.click();
        expect(host.querySelector(".round-list")).toBeNull();
        expect(position(host)).toMatch(/^East 2, 2 honba Step 1 of/);
        expect(document.activeElement).toBe(button(host, ".replay-controls__option--rounds"));
    });

    it("goes from its last row to the replay's last stop, the touch way to the end", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba");
        button(host, ".replay-controls__option--rounds").click();

        button(host, ".round-list__row--end").click();

        expect(host.querySelector(".round-list")).toBeNull();
        expect(position(host)).toBe("East 3 Step 128 of 128");
        expect(button(host, ".replay-controls__move--next").disabled).toBe(true);
    });

    it("closes on Escape and on a click outside it, not on one inside", async () => {
        const { host } = await mountLoadedReplay("double_ron_on_honba");
        button(host, ".replay-controls__option--rounds").click();

        host.querySelector<HTMLElement>(".round-list__head")?.click();
        expect(host.querySelector(".round-list")).not.toBeNull();

        document.body.click();
        expect(host.querySelector(".round-list")).toBeNull();

        button(host, ".replay-controls__option--rounds").click();
        pressKey(document.activeElement ?? host, "Escape");
        expect(host.querySelector(".round-list")).toBeNull();
    });
});

describe("mountReplayView - address", () => {
    it("opens where the address says and keeps it on the position shown, at most once per interval", async () => {
        const { clock, host, written } = await mountLoadedReplay(
            "double_ron_on_honba",
            "?round=2&step=3",
        );
        expect(position(host)).toMatch(/^East 2, 2 honba Step 4 of /);
        expect(written).toEqual(["?round=2&step=3&seat=1"]);

        button(host, ".replay-controls__move--next").click();
        button(host, ".replay-controls__move--next").click();
        expect(written).toHaveLength(1);

        clock.advanceTo(REPLAY_URL_WRITE_INTERVAL_MS);
        expect(written.at(-1)).toBe("?round=2&step=5&seat=1");
    });

    it("writes a waiting address as the page hides, and drops it on dispose", async () => {
        const hidden = await mountLoadedReplay();
        button(hidden.host, ".replay-controls__move--next").click();
        hidden.hidePage();
        expect(hidden.written.at(-1)).toBe("?seat=0&round=0&step=1");

        const disposed = await mountLoadedReplay();
        button(disposed.host, ".replay-controls__move--next").click();
        disposed.dispose();
        disposed.clock.advanceTo(10_000);
        expect(disposed.written).toEqual(["?seat=0&round=0&step=0"]);
    });
});

describe("mountReplayView - loading", () => {
    it("waits for a replay not saved yet and shows it once it is", async () => {
        const { answer, clock, host } = mountReplay();
        await answer({ ok: false, status: 404 });
        expect(textOf(host, ".replay-state")).toBe("Waiting for the replay to be saved…");

        clock.advanceTo(500);
        await answer({ content: engineReplayBytes("riichi"), ok: true });

        expect(position(host)).toBe("East 1 Step 1 of 28");
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

    it("refuses a replay of another version or an undecodable one without offering to try again, its cause on the console alone", async () => {
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});
        const { answer, host } = mountReplay();
        await answer({
            content: encodeReplayLines(
                [
                    JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: "0.1" }),
                    JSON.stringify({ [WIRE_KEY.EVENT_TYPE]: 8 }),
                ].join("\n"),
            ),
            ok: true,
        });
        const undecodable = mountReplay();
        await undecodable.answer({ content: new Uint8Array([129, 161, 49, 1]), ok: true });

        expect([
            textOf(host, ".replay-state__title"),
            host.querySelector(".replay-rotate"),
        ]).toEqual(["This replay cannot be shown", null]);
        expect(textOf(host, ".replay-state__detail")).toBe(
            'It was recorded in format "0.1", which this page cannot read.',
        );
        expect(host.querySelector(".replay-state__links button")).toBeNull();
        expect(textOf(undecodable.host, ".replay-state")).toBe(
            "This replay cannot be shown Record 1 could not be read. Game history Lobby",
        );
        expect(logged).toHaveBeenCalledWith(
            "The replay could not be read:",
            new Error("Unknown replay metadata key: 1"),
        );
    });

    it("says a replay holding no deal holds no round, and which line broke it off", async () => {
        const empty = mountReplay();
        await empty.answer({
            content: encodeReplayLines(
                JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION }),
            ),
            ok: true,
        });
        const damaged = mountReplay();
        await damaged.answer({
            content: encodeReplayLines(
                [JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION }), "not json"].join(
                    "\n",
                ),
            ),
            ok: true,
        });

        expect(textOf(empty.host, ".replay-state__title")).toBe("This replay holds no round");
        expect(textOf(empty.host, ".replay-state__detail")).toBe(
            "The recording stops before the first deal.",
        );
        expect(textOf(damaged.host, ".replay-state__detail")).toBe(
            "The recording stops before the first deal. Record 2 could not be read.",
        );
    });

    it("labels a replay that stops before the game's end, and says where it ends at its last stop", async () => {
        const { host } = await mountLoadedReplay("truncated_mid_round");
        button(host, ".replay-controls__move--last").click();

        expect(textOf(host, ".replay-status__incomplete--end")).toBe(
            "Incomplete The recording ends here, before the game's end Ends here",
        );
    });

    it("says a replay that throws while it is read cannot be shown, without a retry, the error on the console", async () => {
        const thrown = new Error("settings unreadable");
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});
        const { answer, failPrefsLoad, host } = mountReplay();
        failPrefsLoad(thrown);

        await answer({ content: engineReplayBytes("riichi"), ok: true });

        expect(textOf(host, ".replay-state__title")).toBe("This replay cannot be shown");
        expect(host.querySelector(".replay-state__links button")).toBeNull();
        expect(logged).toHaveBeenCalledWith("The replay could not be shown:", thrown);
    });

    it("says a replay that throws while a held button repeats cannot be shown, arming no further repeat", async () => {
        const { links, reads } = drawnLinks();
        vi.spyOn(console, "error").mockImplementation(() => {});
        const { clock, dispose, host } = await mountLoadedReplay("riichi", "?round=0&step=0", {
            links,
        });

        button(host, ".replay-controls__move--next").dispatchEvent(pointer("pointerdown"));
        const pressed = position(host);
        reads.throwing = 1;
        clock.advanceTo(HOLD_DELAY_MS);
        const shown = [
            pressed,
            textOf(host, ".replay-state__title"),
            clock.timers.find((timer) => timer.at === HOLD_DELAY_MS + HOLD_REPEAT_MS),
        ];
        dispose();

        expect([...shown, clock.timers.filter((timer) => !timer.cancelled)]).toEqual([
            "East 1 Step 2 of 28",
            "This replay cannot be shown",
            undefined,
            [],
        ]);
    });

    it("says a replay that throws while autoplay steps cannot be shown, its timers stopped and the error on the console", async () => {
        const { links, reads } = drawnLinks();
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});
        const { clock, host } = await mountLoadedReplay("full_game", "?round=11&step=140", {
            links,
        });
        reads.throwing = 1;

        button(host, ".replay-controls__play").click();
        runTimers(clock);

        expect(textOf(host, ".replay-state__title")).toBe("This replay cannot be shown");
        expect(logged).toHaveBeenCalledWith("The replay could not be shown:", expect.any(Error));
        expect(clock.timers.filter((timer) => !timer.cancelled)).toEqual([]);
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
        await loading.answer({ content: engineReplayBytes("riichi"), ok: true });
        expect(loading.host.childElementCount).toBe(0);
    });
});
