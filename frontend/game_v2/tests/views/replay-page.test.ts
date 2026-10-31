import { assert, describe, expect, it } from "vitest";

import { engineReplayText } from "#tests/fixtures/replays";
import { DEFAULT_REPLAY_PREFS, type ReplayPrefs, roundPosition } from "@/entities/table";
import {
    HOLD_DELAY_MS,
    HOLD_REPEAT_MS,
    type LoadedScreen,
    type ReplayPageEffect,
    type ReplayPageInput,
    type ReplayScreen,
    replayPageDeadline,
    stepReplayPage,
} from "@/views/replay-page";

const LOADING: ReplayScreen = { kind: "loading", waiting: false };

interface OpenOptions {
    readonly autoplay?: boolean;
    readonly prefs?: ReplayPrefs;
}

function opened(
    name: string,
    search = "",
    { autoplay = false, prefs = DEFAULT_REPLAY_PREFS }: OpenOptions = {},
): LoadedScreen {
    const { screen } = stepReplayPage(LOADING, {
        at: 0,
        fetched: { ok: true, text: engineReplayText(name) },
        kind: "fetched",
        opening: { autoplay, prefs, roundListOpen: false, search },
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

function loaded(screen: ReplayScreen): LoadedScreen {
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
): { readonly screens: readonly ReplayScreen[]; readonly effects: readonly ReplayPageEffect[] } {
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

describe("stepReplayPage - loading", () => {
    it("fails a fetch answered 404 as not found and any other status as refused", () => {
        expect(
            [404, 500].map(
                (status) =>
                    step(LOADING, {
                        fetched: { ok: false, status },
                        kind: "fetched",
                        opening: {
                            autoplay: false,
                            prefs: DEFAULT_REPLAY_PREFS,
                            roundListOpen: false,
                            search: "",
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
            fetched: { ok: true, text: engineReplayText("riichi") },
            kind: "fetched",
            opening: {
                autoplay: true,
                prefs: DEFAULT_REPLAY_PREFS,
                roundListOpen: false,
                search: "",
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
            fetched: { ok: true, text: engineReplayText("riichi") },
            kind: "fetched",
            opening: {
                autoplay: true,
                prefs: { hideHands: true, speed: 2 },
                roundListOpen: false,
                search: "",
            },
        });

        expect([where(paused), replayPageDeadline(paused)]).toEqual([[0, 5, 0], null]);
        expect(effects).toEqual([WRITE_ADDRESS]);
        expect([loaded(screen).hideHands, replayPageDeadline(screen)]).toEqual([true, 1800]);
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
        const playing = step(opened("double_ron", "?round=0&step=9"), { kind: "toggle_play" });

        const { effects, screen } = step(playing.screen, { kind: "result_page", page: 1 });

        expect([where(screen), loaded(screen).autoplay.playing, effects]).toEqual([
            [0, 9, 1],
            false,
            [WRITE_ADDRESS],
        ]);
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
        const last = step(opened("riichi"), { command: "last", kind: "key", repeat: false }).screen;

        const toggled = step(last, { kind: "toggle_play" }).screen;

        expect([loaded(toggled).autoplay.playing, replayPageDeadline(toggled)]).toEqual([
            false,
            null,
        ]);
    });

    it("takes its speed from the reader's settings, saves a change and re-arms a playing autoplay at the new pace", () => {
        const playing = step(
            opened("riichi", "", { prefs: { hideHands: false, speed: 4 } }),
            { kind: "toggle_play" },
            0,
        ).screen;

        const { effects, screen } = step(playing, { kind: "cycle_speed" }, 100);

        expect(replayPageDeadline(playing)).toBe(400);
        expect(effects).toEqual([{ kind: "save_prefs", prefs: { hideHands: false, speed: 0.5 } }]);
        expect(replayPageDeadline(screen)).toBe(3300);
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
            { kind: "save_prefs", prefs: { hideHands: true, speed: 1 } },
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

describe("stepReplayPage - view and pin", () => {
    it("switches the view without moving the cursor or the result's page, unpinning the nameplate and saving no settings", () => {
        const { screens } = script(opened("double_ron", "?round=0&step=10"), [
            [{ kind: "result_page", page: 1 }, 0],
            [{ kind: "pin", seat: "left" }, 0],
        ]);
        const pinned = loaded(screens[1]);

        const { effects, screen } = step(pinned, { kind: "switch_view" });

        expect([where(screen), loaded(screen).pinnedNameplate, effects]).toEqual([
            [0, 10, 1],
            null,
            [WRITE_ADDRESS],
        ]);
        expect(loaded(screen).view.bottomSeat).not.toBe(pinned.view.bottomSeat);
    });

    it("keeps a pinned nameplate from step to step, saving neither the settings nor the address", () => {
        const pin = step(opened("riichi"), { kind: "pin", seat: "top" });

        const stepped = step(pin.screen, { command: "next", kind: "key", repeat: false }).screen;

        expect(pin.effects).toEqual([]);
        expect(loaded(stepped).pinnedNameplate).toBe("top");
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
        const press = { direction: "next", kind: "step_press", primary: true } as const;
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
        ["a standings row of a round with no result", { kind: "round_result", round: 99 }],
    ] as const)("leaves the screen as it was on %s", (_name, input) => {
        const start = opened("riichi");

        expect(step(start, input)).toEqual({ effects: [], screen: start });
    });

    it("pauses a turning wheel at a round's result until it rests", () => {
        const { screens } = script(
            opened("double_ron_on_honba", "?round=0&step=139"),
            [0, 160, 320, 600].map((at) => [{ deltaPx: 100, kind: "wheel" }, at] as const),
        );

        expect(screens.map(where)).toEqual([
            [0, 140, 0],
            [0, 140, 0],
            [0, 140, 0],
            [1, 0, 0],
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
