import { assert, describe, expect, it } from "vitest";

import { encodeReplayRecords, joinBytes } from "#tests/fixtures/replay-records";
import { engineReplayBytes } from "#tests/fixtures/replays";
import {
    DEFAULT_REPLAY_PREFS,
    HOLD_DELAY_MS,
    HOLD_REPEAT_MS,
    type LoadedReplayScreen,
    OBSERVE_POLL_MS,
    OBSERVE_RESULT_HOLD_MS,
    type ObserveOpening,
    type ReplayPageEffect,
    type ReplayPageInput,
    type ReplayPrefs,
    type ReplayScreen,
    WHEEL_RESULT_HOLD_MS,
    canStep,
    replayPageDeadline,
    roundPosition,
    stepReplayPage,
} from "@/entities/replay";
import { CALLOUT_MS, readReplayFile } from "@/entities/table";
import { type ObserveFetch } from "@/shared/api";
import { EVENT_TYPE, REPLAY_VERSION, WIRE_KEY } from "@/shared/protocol";

const LOADING: ReplayScreen = { kind: "loading", waiting: false };

interface OpenOptions {
    readonly autoplay?: boolean;
    readonly prefs?: ReplayPrefs;
    readonly soundOn?: boolean;
    readonly animationsOn?: boolean;
}

function opened(
    name: string,
    search = "",
    {
        animationsOn = true,
        autoplay = false,
        prefs = DEFAULT_REPLAY_PREFS,
        soundOn = false,
    }: OpenOptions = {},
): LoadedReplayScreen {
    const { screen } = stepReplayPage(LOADING, {
        at: 0,
        fetched: { content: engineReplayBytes(name), ok: true },
        kind: "fetched",
        opening: { animationsOn, autoplay, prefs, roundListOpen: false, search, soundOn },
    });
    assert(screen.kind === "loaded");
    return screen;
}

function step(
    screen: ReplayScreen,
    input: ReplayPageInput,
    at = 0,
): ReturnType<typeof stepReplayPage> {
    return stepReplayPage(screen, { ...input, at });
}

function loaded(screen: ReplayScreen): LoadedReplayScreen {
    assert(screen.kind === "loaded");
    return screen;
}

/** The screen's position as the address names it, with the result's page. */
function where(screen: ReplayScreen): [number, number, number] {
    const { replay, view } = loaded(screen);
    const { round, step: at } = roundPosition(replay.navigation, view.cursor);
    return [round, at, view.cursor.page];
}

/** Step each input in turn at its time, returning every screen and all the effects asked. */
function script(
    start: ReplayScreen,
    inputs: readonly (readonly [ReplayPageInput, number])[],
): {
    readonly screens: readonly ReplayScreen[];
    readonly effects: readonly ReplayPageEffect[];
} {
    const [first, ...rest] = inputs;
    if (first === undefined) {
        return { effects: [], screens: [] };
    }
    const next = step(start, ...first);
    const later = script(next.screen, rest);
    return {
        effects: [...next.effects, ...later.effects],
        screens: [next.screen, ...later.screens],
    };
}

/** Tick at each deadline the screen holds until it holds none, at most `limit` times. */
function tickThrough(screen: ReplayScreen, limit = 50): ReplayScreen {
    const due = replayPageDeadline(screen);
    return due === null || limit === 0
        ? screen
        : tickThrough(step(screen, { kind: "tick" }, due).screen, limit - 1);
}

const WRITE_ADDRESS = { kind: "write_address" };

/** The first stop that shows calls: a replay's first meld. */
function firstCallStop(screen: LoadedReplayScreen): number {
    const { events, navigation } = screen.replay;
    return navigation.stops.findIndex((stop) => events[stop.moveEntry].type === "meld");
}

/** The stop whose calls the screen shows and whether the board reads them out. */
function shownCallOf(screen: ReplayScreen): [number, boolean] | null {
    const { shownCall } = loaded(screen);
    return shownCall === null ? null : [shownCall.stop, shownCall.announce];
}

describe("stepReplayPage - loading", () => {
    it("fails a fetch answered 404 as not found and any other status as refused", () => {
        expect(
            [404, 500].map(
                (status) =>
                    step(LOADING, {
                        fetched: { ok: false, status },
                        kind: "fetched",
                        opening: {
                            animationsOn: true,
                            autoplay: false,
                            prefs: DEFAULT_REPLAY_PREFS,
                            roundListOpen: false,
                            search: "",
                            soundOn: false,
                        },
                    }).screen,
            ),
        ).toEqual([
            { failure: { kind: "not_found" }, kind: "failed" },
            { failure: { kind: "refused", status: 500 }, kind: "failed" },
        ]);
    });

    it("takes the load's wait, its unreachable server and its fetch only while loading, never once the replay shows", () => {
        const shown = opened("riichi");
        const staleFetch: ReplayPageInput = {
            fetched: { content: engineReplayBytes("riichi"), ok: true },
            kind: "fetched",
            opening: {
                animationsOn: true,
                autoplay: true,
                prefs: DEFAULT_REPLAY_PREFS,
                roundListOpen: false,
                search: "",
                soundOn: false,
            },
        };

        expect(step(LOADING, { kind: "load_waiting" }).screen).toEqual({
            kind: "loading",
            waiting: true,
        });
        expect(step(LOADING, { kind: "load_unreachable" }).screen).toEqual({
            failure: { kind: "unreachable" },
            kind: "failed",
        });
        expect(step(shown, { kind: "load_waiting" }).screen).toBe(shown);
        expect(step(shown, { kind: "load_unreachable" }).screen).toBe(shown);
        expect(step(shown, staleFetch)).toEqual({ effects: [], screen: shown });
    });

    it("opens where the address says and writes it, with autoplay armed from the opening when asked", () => {
        const paused = opened("riichi", "?round=0&step=5");
        const { effects, screen } = stepReplayPage(LOADING, {
            at: 1000,
            fetched: { content: engineReplayBytes("riichi"), ok: true },
            kind: "fetched",
            opening: {
                animationsOn: true,
                autoplay: true,
                prefs: { ...DEFAULT_REPLAY_PREFS, hideHands: true },
                roundListOpen: false,
                search: "",
                soundOn: false,
            },
        });

        expect([where(paused), replayPageDeadline(paused)]).toEqual([[0, 5, 0], null]);
        expect(effects).toEqual([WRITE_ADDRESS]);
        expect([loaded(screen).hideHands, replayPageDeadline(screen)]).toEqual([true, 2600]);
    });

    it("shows the failure screen from a playing replay, its deadline dropped, and loads again on a retry", () => {
        const playing = step(opened("riichi"), { kind: "toggle_play" }).screen;

        const failed = step(playing, { kind: "show_failed" }).screen;

        expect([failed, replayPageDeadline(failed)]).toEqual([
            { failure: { kind: "show_failed" }, kind: "failed" },
            null,
        ]);
        expect(step(failed, { kind: "load_started" }).screen).toEqual(LOADING);
    });
});

describe("stepReplayPage - moving", () => {
    it("moves a round with the round keys and to either end, a move with nowhere to go changing nothing", () => {
        const { effects, screens } = script(opened("double_ron_on_honba", "?round=0&step=5"), [
            [{ command: "nextRound", kind: "key", repeat: false }, 0],
            [{ command: "prevRound", kind: "key", repeat: false }, 0],
            [{ command: "prevRound", kind: "key", repeat: false }, 0],
            [{ command: "last", kind: "key", repeat: false }, 0],
            [{ command: "first", kind: "key", repeat: false }, 0],
        ]);

        expect(screens.map(where)).toEqual([
            [1, 0, 0],
            [0, 0, 0],
            [0, 0, 0],
            [3, 127, 0],
            [0, 0, 0],
        ]);
        expect(screens[2]).toBe(screens[1]);
        expect(effects).toHaveLength(4);
    });

    it("pauses a held key at a round's result, where a fresh press moves on", () => {
        const { screens } = script(opened("double_ron_on_honba", "?round=0&step=139"), [
            [{ command: "next", kind: "key", repeat: true }, 0],
            [{ command: "next", kind: "key", repeat: true }, 30],
            [{ command: "next", kind: "key", repeat: false }, 60],
        ]);

        expect(screens.map(where)).toEqual([
            [0, 140, 0],
            [0, 140, 0],
            [1, 0, 0],
        ]);
    });

    it("pages a double ron's result as a move of its own, stopping autoplay", () => {
        const playing = step(opened("double_ron", "?round=0&step=9"), {
            kind: "toggle_play",
        });

        const { effects, screen } = step(playing.screen, {
            kind: "result_page",
            page: 1,
        });

        expect([where(screen), loaded(screen).autoplay.playing, effects]).toEqual([
            [0, 9, 1],
            false,
            [WRITE_ADDRESS],
        ]);
    });

    it("keeps a call showing as the reader moves on until its time is up, never back before it", () => {
        const start = opened("kans");
        const kan = firstCallStop(start);
        const next = { command: "next", kind: "key", repeat: false } as const;
        const onKan = step(start, { cursor: { page: 0, stop: kan }, kind: "move" }).screen;
        const movedOn = step(onKan, next, 1000).screen;
        const late = step(onKan, next, CALLOUT_MS).screen;
        const back = step(
            movedOn,
            { cursor: { page: 0, stop: kan - 1 }, kind: "move" },
            1000,
        ).screen;

        expect(
            [onKan, movedOn, late, back].map((screen) => loaded(screen).shownCall?.stop ?? null),
        ).toEqual([kan, kan, null, null]);
    });

    it("announces a call shown by a step on or back and by autoplay", () => {
        const start = opened("kans");
        const kan = firstCallStop(start);
        const before = step(start, { cursor: { page: 0, stop: kan - 1 }, kind: "move" }).screen;
        const after = step(start, { cursor: { page: 0, stop: kan + 1 }, kind: "move" }).screen;
        const playing = step(before, { kind: "toggle_play" }).screen;

        const shown = [
            step(before, { direction: "next", kind: "step_press", primary: true }).screen,
            step(before, { command: "next", kind: "key", repeat: false }).screen,
            step(after, { direction: "prev", kind: "step_click" }).screen,
            step(playing, { kind: "tick" }, replayPageDeadline(playing) ?? 0).screen,
        ];

        expect(shown.map(shownCallOf)).toEqual(shown.map(() => [kan, true]));
    });

    it("shows a call reached by a jump, a held Next or the wheel without announcing it", () => {
        const start = opened("kans");
        const kan = firstCallStop(start);
        const { round, step: at } = roundPosition(start.replay.navigation, { page: 0, stop: kan });
        const twoBefore = step(start, { cursor: { page: 0, stop: kan - 2 }, kind: "move" }).screen;
        const before = step(start, { cursor: { page: 0, stop: kan - 1 }, kind: "move" }).screen;
        const pressed = step(twoBefore, {
            direction: "next",
            kind: "step_press",
            primary: true,
        }).screen;

        const shown = [
            opened("kans", `?round=${round}&step=${at}`),
            step(start, { cursor: { page: 0, stop: kan }, kind: "move" }).screen,
            step(pressed, { kind: "tick" }, HOLD_DELAY_MS).screen,
            step(before, { command: "next", kind: "key", repeat: true }).screen,
            step(before, { deltaPx: 100, kind: "wheel" }).screen,
        ];

        expect(shown.map(shownCallOf)).toEqual(shown.map(() => [kan, false]));
    });

    it("keeps a silently shown call silent when the reader steps on while it still shows", () => {
        const start = opened("kans");
        const kan = firstCallStop(start);
        const onKan = step(start, { cursor: { page: 0, stop: kan }, kind: "move" }).screen;

        const movedOn = step(onKan, { command: "next", kind: "key", repeat: false }, 1000).screen;

        expect(shownCallOf(movedOn)).toEqual([kan, false]);
    });
});

describe("stepReplayPage - autoplay", () => {
    it("plays on and pauses on a round's result, moving on from it when played again", () => {
        const start = step(opened("double_ron_on_honba", "?round=0&step=137"), {
            kind: "toggle_play",
        }).screen;
        const early = step(start, { kind: "tick" }, (replayPageDeadline(start) ?? 0) - 1).screen;
        const paused = tickThrough(start);
        const moved = tickThrough(step(paused, { kind: "toggle_play" }, 10_000).screen, 1);

        expect(early).toBe(start);
        expect([where(paused), loaded(paused).autoplay.playing]).toEqual([[0, 140, 0], false]);
        expect([where(moved), loaded(moved).autoplay.playing]).toEqual([[1, 0, 0], true]);
    });

    it("does not play from the last stop", () => {
        const last = step(opened("riichi"), {
            command: "last",
            kind: "key",
            repeat: false,
        }).screen;

        const toggled = step(last, { kind: "toggle_play" }).screen;

        expect([loaded(toggled).autoplay.playing, replayPageDeadline(toggled)]).toEqual([
            false,
            null,
        ]);
    });

    it("switches autoplay, the view and the hands once per press however long the key is held", () => {
        const start = opened("riichi");
        const { effects, screens } = script(
            start,
            (["play", "hands", "view"] as const).flatMap((command) => [
                [{ command, kind: "key", repeat: false }, 0] as const,
                [{ command, kind: "key", repeat: true }, 30] as const,
            ]),
        );
        const end = loaded(screens.at(-1) ?? start);

        expect([end.autoplay.playing, end.hideHands, end.view.bottomSeat]).toEqual([
            true,
            true,
            (start.view.bottomSeat + 1) % start.replay.seatCount,
        ]);
        expect(effects).toEqual([
            { kind: "save_prefs", prefs: { hideHands: true, showTsumogiri: true } },
            WRITE_ADDRESS,
        ]);
    });

    it("stops autoplay and a hold as the page hides, writing nothing", () => {
        const playing = step(opened("riichi"), { kind: "toggle_play" }).screen;
        const held = step(opened("riichi"), {
            direction: "next",
            kind: "step_press",
            primary: true,
        }).screen;

        const hidden = [playing, held].map((screen) => step(screen, { kind: "page_hide" }));

        expect(hidden.map(({ effects, screen }) => [replayPageDeadline(screen), effects])).toEqual([
            [null, []],
            [null, []],
        ]);
    });
});

describe("stepReplayPage - view", () => {
    it("views from a chosen seat without moving the cursor or the result's page, and the bottom's own changes nothing", () => {
        const onPage = step(opened("double_ron", "?round=0&step=10"), {
            kind: "result_page",
            page: 1,
        }).screen;
        const { bottomSeat } = loaded(onPage).view;

        const top = step(onPage, { kind: "view_seat", seat: "top" });
        const bottom = step(top.screen, { kind: "view_seat", seat: "bottom" });

        expect([where(top.screen), loaded(top.screen).view.bottomSeat, top.effects]).toEqual([
            [0, 10, 1],
            (bottomSeat + 2) % 4,
            [WRITE_ADDRESS],
        ]);
        expect(bottom).toEqual({ effects: [], screen: top.screen });
    });
});

/** The sounds a step asks the view to play. */
function soundsOf(effects: readonly ReplayPageEffect[]): readonly string[] {
    return effects.flatMap((effect) => (effect.kind === "play_sounds" ? effect.cues : []));
}

describe("stepReplayPage - sound", () => {
    it("plays a step on's sounds, a riichi's with its discard's click, and none for a step back, a jump or with the sound off", () => {
        function atStep(soundOn: boolean): LoadedReplayScreen {
            return opened("riichi", "?round=0&step=10", { soundOn });
        }
        const next = { command: "next", kind: "key", repeat: false } as const;
        const stepped = step(atStep(true), next);
        const back = step(stepped.screen, { command: "prev", kind: "key", repeat: false });
        const jumpTo = { page: 0, stop: atStep(true).view.cursor.stop + 2 };
        const jumped = step(atStep(true), { cursor: jumpTo, kind: "move" });

        expect([atStep(true).seating, atStep(false).seating]).toEqual([true, false]);
        expect(
            [stepped, back, jumped, step(atStep(false), next)].map(({ effects }) =>
                soundsOf(effects),
            ),
        ).toEqual([["discard", "riichi"], [], [], []]);
    });

    it("turns the sound off and on, asking the view to keep each turn", () => {
        const off = step(opened("riichi", "", { soundOn: true }), { kind: "toggle_sound" });
        const on = step(off.screen, { kind: "toggle_sound" });

        expect([loaded(off.screen).soundOn, off.effects, on.effects]).toEqual([
            false,
            [{ kind: "save_sound", soundOn: false }],
            [{ kind: "save_sound", soundOn: true }],
        ]);
    });

    it("turns the animations off, asking the view to keep the turn and leaving the sound alone", () => {
        const { effects, screen } = step(opened("riichi", "", { soundOn: true }), {
            kind: "toggle_animations",
        });

        expect([loaded(screen).animationsOn, loaded(screen).soundOn, effects]).toEqual([
            false,
            true,
            [{ animationsOn: false, kind: "save_animations" }],
        ]);
    });
});

describe("stepReplayPage - hold and wheel", () => {
    it("repeats a held step button after a delay and on a beat, ending at a round's result", () => {
        const pressed = step(opened("double_ron_on_honba", "?round=0&step=136"), {
            direction: "next",
            kind: "step_press",
            primary: true,
        }).screen;

        const { screens } = script(pressed, [
            [{ kind: "tick" }, HOLD_DELAY_MS - 1],
            [{ kind: "tick" }, HOLD_DELAY_MS],
            [{ kind: "tick" }, HOLD_DELAY_MS + HOLD_REPEAT_MS],
            [{ kind: "tick" }, HOLD_DELAY_MS + 2 * HOLD_REPEAT_MS],
            [{ kind: "tick" }, HOLD_DELAY_MS + 3 * HOLD_REPEAT_MS],
        ]);

        expect([where(pressed), replayPageDeadline(pressed)]).toEqual([[0, 137, 0], HOLD_DELAY_MS]);
        expect(screens.map((screen) => [where(screen), replayPageDeadline(screen)])).toEqual([
            [[0, 137, 0], HOLD_DELAY_MS],
            [[0, 138, 0], HOLD_DELAY_MS + HOLD_REPEAT_MS],
            [[0, 139, 0], HOLD_DELAY_MS + 2 * HOLD_REPEAT_MS],
            [[0, 140, 0], HOLD_DELAY_MS + 3 * HOLD_REPEAT_MS],
            [[0, 140, 0], null],
        ]);
    });

    it("drops a hold when another move takes over or autoplay starts", () => {
        const press = {
            direction: "next",
            kind: "step_press",
            primary: true,
        } as const;
        const { screens } = script(opened("riichi", "?round=0&step=5"), [
            [press, 0],
            [{ command: "prev", kind: "key", repeat: false }, 10],
            [press, 20],
            [{ kind: "toggle_play" }, 30],
        ]);
        const [, moved, , playing] = screens.map(loaded);

        expect([where(moved), moved.hold, replayPageDeadline(moved)]).toEqual([
            [0, 5, 0],
            null,
            null,
        ]);
        expect([playing.hold, playing.autoplay.playing]).toEqual([null, true]);
    });

    it("leaves the click to step after a cancelled press, and takes no step from a press of another button", () => {
        const start = opened("riichi");
        const { screens } = script(start, [
            [{ direction: "next", kind: "step_press", primary: true }, 0],
            [{ cancelled: true, kind: "hold_end" }, 10],
            [{ direction: "next", kind: "step_click" }, 10],
            [{ direction: "next", kind: "step_press", primary: false }, 20],
        ]);

        expect(screens.map(where)).toEqual([
            [0, 1, 0],
            [0, 1, 0],
            [0, 2, 0],
            [0, 2, 0],
        ]);
        expect(loaded(screens[3]).hold).toBeNull();
    });

    it.each([
        ["a held pointer with no hold", { kind: "hold_pointer", over: false }],
        ["a hold's end with no hold", { cancelled: false, kind: "hold_end" }],
        ["a wheel back from the first stop", { deltaPx: -100, kind: "wheel" }],
        ["a wheel on the seating, which no wheel leaves", { deltaPx: 100, kind: "wheel" }],
    ] as const)("leaves the screen as it was on %s", (_name, input) => {
        const start = opened("riichi");

        expect(step(start, input)).toEqual({ effects: [], screen: start });
    });

    it("holds each page of a double ron's result for a beat under a turning wheel", () => {
        const hold = WHEEL_RESULT_HOLD_MS;
        const { screens } = script(
            opened("double_ron", "?round=0&step=9"),
            [0, 100, hold, hold + 100].map((at) => [{ deltaPx: 100, kind: "wheel" }, at] as const),
        );

        expect(screens.map(where)).toEqual([
            [0, 10, 0],
            [0, 10, 0],
            [0, 10, 1],
            [0, 10, 1],
        ]);
    });
});

describe("stepReplayPage - round list", () => {
    it("opens on the current row, closes back to its toggle, and an outside click dismisses it where the focus is", () => {
        const start = opened("double_ron_on_honba");
        const open = step(start, { kind: "toggle_round_list" }).screen;

        const steps = [
            step(start, { kind: "toggle_round_list" }),
            step(open, { kind: "toggle_round_list" }),
            step(open, { kind: "close_round_list" }),
            step(open, { kind: "dismiss_round_list" }),
        ];

        expect(steps.map(({ effects, screen }) => [loaded(screen).roundListOpen, effects])).toEqual(
            [
                [true, [{ kind: "focus", target: "current_round" }]],
                [false, [{ kind: "focus", target: "round_list_toggle" }]],
                [false, [{ kind: "focus", target: "round_list_toggle" }]],
                [false, []],
            ],
        );
        expect(step(start, { kind: "dismiss_round_list" }).screen).toBe(start);
    });
});

describe("stepReplayPage - settings", () => {
    it("closes the settings menu when the reader moves", () => {
        const open = step(opened("riichi", "?round=0&step=10"), { kind: "toggle_settings" }).screen;
        const inputs: readonly ReplayPageInput[] = [
            { command: "next", kind: "key", repeat: false },
            { kind: "toggle_round_list" },
            { kind: "toggle_sound" },
        ];

        expect(inputs.map((input) => loaded(step(open, input).screen).settingsOpen)).toEqual([
            false,
            false,
            true,
        ]);
    });
});

const OBSERVE_OPENING: ObserveOpening = {
    animationsOn: true,
    prefs: DEFAULT_REPLAY_PREFS,
    roundListOpen: false,
    soundOn: false,
};

const PLAYERS = ["Akagi", "Washizu", "Ten", "Hiro"];

/** An engine replay as its observe stream sends it: each event record, its game start without the seed. */
function observeRecords(name: string): readonly Uint8Array[] {
    const file = readReplayFile(engineReplayBytes(name));
    assert(file.ok);
    return file.lines.map(({ raw }) =>
        encodeReplayRecords([
            Object.fromEntries(
                Object.entries(raw).filter(([key]) => Number(key) !== WIRE_KEY.SEED),
            ),
        ]),
    );
}

const VERSION_RECORD = encodeReplayRecords([{ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION }]);

/** The index of the first record of `type` at or after `from`. */
function recordIndex(name: string, type: number, from = 0): number {
    const file = readReplayFile(engineReplayBytes(name));
    assert(file.ok);
    const found = file.lines.findIndex(
        ({ raw }, index) => index >= from && raw[WIRE_KEY.EVENT_TYPE] === type,
    );
    assert(found !== -1);
    return found;
}

interface AnswerOptions {
    readonly availableInMs?: number;
    readonly ended?: boolean;
}

/** An observe answer carrying records `from` up to `to` of the stream, the version record first when from 0. */
function answer(
    records: readonly Uint8Array[],
    [from, to]: readonly [number, number],
    { availableInMs = 0, ended = false }: AnswerOptions = {},
): ReplayPageInput {
    const carried = records.slice(from, to);
    const bytes = joinBytes(
        from === 0 && carried.length > 0 ? [VERSION_RECORD, ...carried] : carried,
    );
    const fetched: ObserveFetch = {
        answer: {
            availableInMs,
            ended,
            gameType: "hanchan",
            next: from + carried.length,
            players: PLAYERS,
            records: bytes,
            startedAt: 0,
        },
        ok: true,
    };
    return { fetched, kind: "observe_fetched", opening: OBSERVE_OPENING };
}

/** Tick at each deadline the screen holds until it holds none, every effect asked on the way. */
function tickAll(screen: ReplayScreen): {
    readonly screen: ReplayScreen;
    readonly effects: readonly ReplayPageEffect[];
} {
    let shown = screen;
    const effects: ReplayPageEffect[] = [];
    for (let due = replayPageDeadline(shown); due !== null; due = replayPageDeadline(shown)) {
        const ticked = step(shown, { kind: "tick" }, due);
        shown = ticked.screen;
        effects.push(...ticked.effects);
    }
    return { effects, screen: shown };
}

function observeOf(screen: ReplayScreen): NonNullable<LoadedReplayScreen["observe"]> {
    const { observe } = loaded(screen);
    assert(observe !== null);
    return observe;
}

/** What a waiting observe screen shows of its countdown, the effects that reached it and its next deadline. */
function countdownShown(stepped: ReturnType<typeof stepReplayPage>): Record<string, unknown> {
    assert(stepped.screen.kind === "observe_waiting");
    return {
        deadline: replayPageDeadline(stepped.screen),
        effects: stepped.effects,
        players: stepped.screen.countdown?.players,
        remainingMs: stepped.screen.countdown?.remainingMs,
    };
}

/** A viewer who arrived before the delay passed: the countdown, its redraw and poll, then the first records. */
function countdownScenario(): Record<
    "asked" | "counting" | "hidden" | "redrawn" | "started",
    ReturnType<typeof stepReplayPage>
> & { readonly shown: ReplayScreen } {
    const records = observeRecords("pao");
    const started = step(LOADING, { kind: "observe_started" }, 0);
    const counting = step(started.screen, answer(records, [0, 0], { availableInMs: 2500 }), 100);
    const redrawn = step(counting.screen, { kind: "tick" }, 600);
    const asked = step(redrawn.screen, { kind: "tick" }, 100 + OBSERVE_POLL_MS);
    const firstDiscard = recordIndex("pao", EVENT_TYPE.DISCARD);
    const { screen: shown } = step(asked.screen, answer(records, [0, firstDiscard + 1]), 2200);
    return {
        asked,
        counting,
        hidden: step(shown, { kind: "page_hide" }, 2300),
        redrawn,
        shown,
        started,
    };
}

/**
 * A late viewer opened on the first round up to its result, viewing from another seat and waiting at the newest stop,
 * then the records through the result to the next round's first discard.
 */
function extendedScenario(): {
    readonly records: readonly Uint8Array[];
    readonly lastDiscard: number;
    readonly first: ReplayScreen;
    readonly viewed: ReplayScreen;
    readonly waiting: ReturnType<typeof stepReplayPage>;
    readonly extended: ReplayScreen;
} {
    const records = observeRecords("full_game");
    const roundEnd = recordIndex("full_game", EVENT_TYPE.ROUND_END);
    const lastDiscard = recordIndex("full_game", EVENT_TYPE.DISCARD, roundEnd);
    const { screen: first } = step(
        step(LOADING, { kind: "observe_started" }).screen,
        answer(records, [0, roundEnd]),
    );
    const { screen: viewed } = step(first, { kind: "view_seat", seat: "right" }, 10);
    const waiting = step(viewed, { kind: "tick" }, replayPageDeadline(viewed) ?? 0);
    const extended = step(waiting.screen, answer(records, [roundEnd, lastDiscard + 1]), 5000);
    return { extended: extended.screen, first, lastDiscard, records, viewed, waiting };
}

/** The extended replay played on: the result, the next deal, the newest stop, then the stream's end played out. */
function playedOnScenario({
    extended,
    lastDiscard,
    records,
}: ReturnType<typeof extendedScenario>): Record<"atResult" | "crossed" | "newest", ReplayScreen> & {
    readonly ended: ReturnType<typeof tickAll>;
} {
    const { screen: atResult } = step(extended, { kind: "tick" }, 5000);
    const { screen: crossed } = step(atResult, { kind: "tick" }, 5000 + OBSERVE_RESULT_HOLD_MS);
    const { screen: newest } = tickAll(crossed);
    const rest = answer(records, [lastDiscard + 1, records.length], { ended: true });
    const ended = tickAll(step(newest, rest, 9000).screen);
    return { atResult, crossed, ended, newest };
}

/** A viewer who saw the countdown, then got the whole game in one answer that ends the stream, played out. */
function endedScenario(): {
    readonly whole: ReplayScreen;
    readonly played: ReturnType<typeof tickAll>;
} {
    const records = observeRecords("pao");
    const counting = step(
        step(LOADING, { kind: "observe_started" }).screen,
        answer(records, [0, 0], { availableInMs: 1000 }),
    ).screen;
    const { screen: whole } = step(
        counting,
        answer(records, [0, records.length], { ended: true }),
        1000,
    );
    return { played: tickAll(whole), whole };
}

/** A late viewer waiting at the newest stop before the round's result, whose next request is answered 404. */
function goneScenario(): {
    readonly roundEnd: number;
    readonly waiting: ReturnType<typeof tickAll>;
    readonly gone: ReplayScreen;
} {
    const records = observeRecords("pao");
    const roundEnd = recordIndex("pao", EVENT_TYPE.ROUND_END);
    const waiting = tickAll(
        step(step(LOADING, { kind: "observe_started" }).screen, answer(records, [0, roundEnd]))
            .screen,
    );
    const notFound: ReplayPageInput = {
        fetched: { ok: false, status: 404 },
        kind: "observe_fetched",
        opening: OBSERVE_OPENING,
    };
    return { gone: step(waiting.screen, notFound, 3000).screen, roundEnd, waiting };
}

function polls(effects: readonly ReplayPageEffect[]): readonly ReplayPageEffect[] {
    return effects.filter((effect) => effect.kind === "fetch_observe");
}

describe("stepReplayPage - observe", () => {
    it("counts down over the players with no records, asks again once due, and opens the first records at the first deal, playing on as the page hides", () => {
        const { asked, counting, hidden, redrawn, shown, started } = countdownScenario();

        expect(started.effects).toEqual([{ from: 0, kind: "fetch_observe" }]);
        expect(countdownShown(counting)).toEqual({
            deadline: 600,
            effects: [],
            players: PLAYERS,
            remainingMs: 2500,
        });
        expect(countdownShown(redrawn)).toMatchObject({ deadline: 1600, remainingMs: 2000 });
        expect(countdownShown(asked)).toMatchObject({
            deadline: 2600,
            effects: [{ from: 0, kind: "fetch_observe" }],
            remainingMs: 500,
        });
        const { autoplay, observe, replay, seating, view } = loaded(shown);
        expect([view.cursor, view.bottomSeat, autoplay.playing, seating]).toEqual([
            replay.opening,
            replay.firstDealerSeat,
            true,
            false,
        ]);
        expect([observe?.pollAt, loaded(hidden.screen).autoplay]).toEqual([
            2200 + OBSERVE_POLL_MS,
            autoplay,
        ]);
    });

    it("ignores every move of the cursor and autoplay's switch, the next seat's view still turning", () => {
        const { shown } = countdownScenario();
        const moves: readonly ReplayPageInput[] = [
            { command: "next", kind: "key", repeat: false },
            { command: "play", kind: "key", repeat: false },
            { deltaPx: 400, kind: "wheel" },
            { direction: "next", kind: "step_press", primary: true },
            { cursor: { page: 0, stop: 1 }, kind: "select_round" },
            { kind: "toggle_play" },
        ];
        const viewed = step(shown, { command: "view", kind: "key", repeat: false }, 2300);

        expect(moves.filter((input) => step(shown, input, 2300).screen !== shown)).toEqual([]);
        expect([canStep(shown, "next"), loaded(viewed.screen).view.bottomSeat]).toEqual([
            false,
            (loaded(shown).view.bottomSeat + 1) % 4,
        ]);
    });

    it("extends the replay in place, autoplay crossing a round's result and the next deal, waiting at the newest stop until the stream ends", () => {
        const extension = extendedScenario();
        const { atResult, crossed, ended, newest } = playedOnScenario(extension);
        const { extended, first, viewed, waiting } = extension;

        expect([
            loaded(first).view.cursor,
            waiting.effects,
            loaded(waiting.screen).autoplay,
        ]).toEqual([lastCursor(first), [], { dueAt: null, playing: true }]);
        expect([loaded(extended).view, loaded(extended).autoplay.dueAt]).toEqual([
            loaded(viewed).view,
            5000,
        ]);
        expect([loaded(atResult).view.cursor.stop, loaded(atResult).autoplay.dueAt]).toEqual([
            loaded(atResult).replay.navigation.rounds[0].resultStop,
            5000 + OBSERVE_RESULT_HOLD_MS,
        ]);
        expect([where(crossed), where(newest)[0], loaded(newest).autoplay]).toEqual([
            [1, 0, 0],
            1,
            { dueAt: null, playing: true },
        ]);
        const { autoplay, replay, view } = loaded(ended.screen);
        expect([view.cursor, replay.navigation.complete, autoplay.playing]).toEqual([
            lastCursor(ended.screen),
            true,
            false,
        ]);
        expect(polls(ended.effects)).toEqual([]);
    });

    it("stops asking once the stream has ended and plays on from what it holds, and keeps the board on a late 404", () => {
        const { played, whole } = endedScenario();
        const { gone, roundEnd, waiting } = goneScenario();

        expect([observeOf(whole).pollAt, loaded(whole).view.cursor]).toEqual([
            null,
            loaded(whole).replay.opening,
        ]);
        expect([polls(played.effects), loaded(played.screen).autoplay.playing]).toEqual([
            [],
            false,
        ]);
        expect(loaded(played.screen).view.cursor).toEqual(lastCursor(played.screen));
        expect(polls(waiting.effects)).toEqual([{ from: roundEnd, kind: "fetch_observe" }]);
        expect([
            loaded(gone).replay,
            loaded(gone).view,
            observeOf(gone).gone,
            loaded(gone).autoplay.playing,
            replayPageDeadline(gone),
        ]).toEqual([loaded(waiting.screen).replay, loaded(waiting.screen).view, true, false, null]);
    });
});

function lastCursor(screen: ReplayScreen): { readonly stop: number; readonly page: number } {
    const { stops } = loaded(screen).replay.navigation;
    const stop = stops.length - 1;
    return { page: stops[stop].pages - 1, stop };
}
