import { assert, describe, expect, it } from "vitest";

import { clientEvent, clientScenario } from "#tests/fixtures/scenario";
import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    wireGameError,
    wireRoundEnd,
    wireSessionError,
} from "#tests/fixtures/wire";
import {
    type GameClientState,
    NO_PLAY_UI,
    type PlayDisplay,
    nextCountdownChange,
    nextDeadline,
    nextPlayUi,
    playDisplay,
    stepGameClient,
} from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";
import { type HandTile, type MeldTile } from "@/entities/tile";
import { buildChiAction } from "@/shared/protocol";

const KUIKAE_BLOCKED = [9, 10, 11];
const CHOOSE_CHI = { kind: "toggle_tile_choice", offer: "chi" } as const;
const CLOSED_KAN_OFFSET = 6072;

/** The viewer's hand on the board as `[tileId, mark]`, the drawn tile last, an unmarked tile as "idle". */
function handMarks(display: PlayDisplay): [number | undefined, string][] {
    const bottom = display.board?.players[0];
    const tiles: HandTile[] = [
        ...(bottom?.hand ?? []),
        ...(bottom?.drawnTile ? [bottom.drawnTile] : []),
    ];
    return tiles.map((tile) => [tile.tileId, tile.state ?? "idle"]);
}

/** A choice's tiles as they lie, `kind face` each, or null for a control with none. */
function laid(group: readonly MeldTile[] | null): string[] | null {
    return (
        group?.map((tile) =>
            tile.kind === "stacked"
                ? `stacked ${tile.bottom}/${tile.top}`
                : `${tile.kind} ${tile.face}`,
        ) ?? null
    );
}

/** The state once logical time reaches the open decision's deadline, which shows it as expired. */
function pastDeadline(state: GameClientState): GameClientState {
    const at = state.decision?.deadline ?? Number.NaN;
    return stepGameClient(state, { at, kind: "tick" }).state;
}

/** How each seat's hand shows on the viewer's board (bottom, right, top, left): "face", "concealed" or both. */
function handShows(state: GameClientState): string[] {
    return (playDisplay(state, NO_PLAY_UI).board?.players ?? []).map((player) =>
        [...new Set(player.hand.map((tile) => tile.show))].join(","),
    );
}

function viewerTiles(state: GameClientState): readonly number[] {
    return state.table.players.find((player) => player.seat === state.viewerSeat)?.tiles ?? [];
}

describe("playDisplay", () => {
    it("shows a call prompt as one control per kind of offer, in the server's order, then Pass, still once expired, and no tile plays", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const display = playDisplay(state, NO_PLAY_UI);
        const expired = playDisplay(pastDeadline(state), NO_PLAY_UI);

        expect(
            display.actions.map((action) => [
                action.label,
                action.tiles,
                action.rank,
                action.pressed,
            ]),
        ).toEqual([
            ["Kan", ["3m"], "call", null],
            ["Pon", ["3m"], "call", null],
            ["Chi", [], "call", false],
            ["Pass", [], "pass", null],
        ]);
        expect(display.actions[1].command).toEqual({
            intent: { offer: { kind: "pon", tileId: 8 }, type: "choose" },
            kind: "intent",
        });
        expect([display.countdown, display.tileIntents.size]).toEqual([
            { kind: "running", move: "call", secondsLeft: 5, turn: null },
            0,
        ]);
        expect(handMarks(display).every(([, mark]) => mark === "waiting")).toBe(true);
        expect(expired.actions).toEqual(display.actions);
        expect([display.decisionStanding, expired.decisionStanding, expired.countdown]).toEqual([
            "open",
            "expired",
            { kind: "expired", move: "call" },
        ]);
    });

    it("on the turn after a chi disables the types kuikae blocks and lets every other tile discard, expired too", () => {
        const state = checkpointState("call_prompt_seat_1", "turn");
        const display = playDisplay(state, NO_PLAY_UI);
        const expired = playDisplay(pastDeadline(state), NO_PLAY_UI);

        const selectable = viewerTiles(state).filter((tileId) => !KUIKAE_BLOCKED.includes(tileId));
        expect(handMarks(display).filter(([, mark]) => mark === "disabled")).toEqual(
            KUIKAE_BLOCKED.map((tileId) => [tileId, "disabled"]),
        );
        expect([...display.tileIntents]).toEqual(
            selectable.map((tileId) => [tileId, { tileId, type: "discard" }]),
        );
        expect(display.actions).toEqual([]);
        expect([...expired.tileIntents]).toEqual([...display.tileIntents]);
        expect(expired.countdown?.kind).toBe("expired");
    });

    it("in riichi lets only the drawn tile discard, offers tsumo and shows the seat's furiten", () => {
        const state = checkpointState("own_turn_seat_1", "tsumo draw");
        const drawn = state.table.players.find((player) => player.seat === 1)?.drawnTileId;
        const display = playDisplay(state, NO_PLAY_UI);

        expect([...display.tileIntents.keys()]).toEqual([drawn]);
        expect(handMarks(display).filter(([, mark]) => mark === "selectable")).toEqual([
            [drawn, "selectable"],
        ]);
        expect(display.actions.map((action) => action.label)).toEqual(["Tsumo"]);
        expect(display.furiten).toBe(true);
    });

    it("while riichi's discard is picked lets only riichi's tiles play, as riichi, until toggled off or a newer wait", () => {
        const state = checkpointState("own_turn_seat_1", "rinshan");
        const toggle = { kind: "toggle_riichi_pick" } as const;
        const picking = nextPlayUi(state, NO_PLAY_UI, toggle);
        const display = playDisplay(state, picking);
        const stale = playDisplay(state, {
            ...NO_PLAY_UI,
            riichiPickWaitId: (state.decision?.waitId ?? 0) - 1,
        });

        expect([...display.tileIntents]).toEqual([
            [120, { offer: { kind: "riichi", tileId: 120 }, type: "choose" }],
        ]);
        expect(handMarks(display).filter(([, mark]) => mark !== "disabled")).toEqual([
            [120, "declaring"],
        ]);
        expect([display.tileAction, display.actions[0].pressed]).toEqual([
            "Declare riichi discarding",
            true,
        ]);
        expect([
            nextPlayUi(state, picking, toggle),
            display.escape,
            nextPlayUi(state, picking, { kind: "step_back" }),
        ]).toEqual([NO_PLAY_UI, { kind: "step_back" }, NO_PLAY_UI]);
        expect([stale.tileAction, stale.tileIntents.get(120), stale.tileIntents.size]).toEqual([
            "Discard",
            { tileId: 120, type: "discard" },
            viewerTiles(state).length,
        ]);
    });

    it("turns a double ron's result to the page asked for, kept through a reconnect's copy of it, not by a newer round", () => {
        const roundEnd = checkpointState("double_ron_seat_1", "round end");
        const reconnected = checkpointState("double_ron_seat_1", "reconnected");
        const nextRound = checkpointState("chankan_robbed_seat_1", "round end");
        const secondPage = nextPlayUi(roundEnd, NO_PLAY_UI, { kind: "show_result_page", page: 1 });
        const pastLast = nextPlayUi(roundEnd, NO_PLAY_UI, { kind: "show_result_page", page: 4 });

        expect(
            [NO_PLAY_UI, secondPage, pastLast].map((ui) => playDisplay(roundEnd, ui).resultPage),
        ).toEqual([0, 1, 1]);
        expect(reconnected.table.roundEndResult).not.toBe(roundEnd.table.roundEndResult);
        expect(playDisplay(reconnected, secondPage).resultPage).toBe(1);
        expect(playDisplay(nextRound, secondPage).resultPage).toBe(0);
    });

    it("pages a double ron's owed result with Next, then confirms it on the last page, counting down", () => {
        const roundEnd = checkpointState("double_ron_seat_1", "round end");
        const lastPage = nextPlayUi(roundEnd, NO_PLAY_UI, { kind: "show_result_page", page: 1 });
        const first = playDisplay(roundEnd, NO_PLAY_UI).result;
        const last = playDisplay(roundEnd, lastPage).result;

        expect(first).toEqual({
            action: {
                command: { kind: "show_result_page", page: 1 },
                label: "Next",
                pressed: null,
                tiles: [],
            },
            countdown: { kind: "running", move: "result", secondsLeft: 20, turn: null },
            waiting: false,
        });
        expect(last?.action).toMatchObject({
            command: { intent: { type: "confirm_result" }, kind: "intent" },
            label: "OK",
        });
    });

    it("once the result is confirmed shows that the seat waits for the others, still counting down", () => {
        const confirmed = checkpointState("chankan_robbed_seat_3", "confirmed");

        expect(playDisplay(confirmed, NO_PLAY_UI).result).toEqual({
            action: null,
            countdown: { kind: "running", move: "result", secondsLeft: 9, turn: null },
            waiting: true,
        });
        expect(nextCountdownChange(confirmed)).toBeGreaterThan(confirmed.now);
    });

    it("shows the game's last result over the standings with the way to them, then the standings", () => {
        const gameEnd = checkpointState("final_round_seat_1", "game end");
        const display = playDisplay(gameEnd, NO_PLAY_UI);
        const dismissed = stepGameClient(gameEnd, {
            at: gameEnd.now,
            intent: { type: "confirm_result" },
            kind: "intent",
        }).state;

        expect([display.resultOverStandings, display.result?.action?.label]).toEqual([
            true,
            "Standings",
        ]);
        expect(display.result?.countdown).toBeNull();
        expect([
            playDisplay(dismissed, NO_PLAY_UI).resultOverStandings,
            playDisplay(dismissed, NO_PLAY_UI).result,
        ]).toEqual([false, null]);
    });

    it("offers the game's last result again from the standings, reopening it on its first page", () => {
        const gameEnd = checkpointState("final_round_seat_1", "game end");
        const dismissed = stepGameClient(gameEnd, {
            at: gameEnd.now,
            intent: { type: "confirm_result" },
            kind: "intent",
        });
        const { lastResult } = playDisplay(dismissed.state, NO_PLAY_UI);
        assert(lastResult?.command.kind === "intent");
        const reopened = stepGameClient(dismissed.state, {
            at: gameEnd.now,
            intent: lastResult.command.intent,
            kind: "intent",
        });
        const turned = { ...NO_PLAY_UI, resultPage: { page: 1, round: "any" } };

        expect([playDisplay(gameEnd, NO_PLAY_UI).lastResult, lastResult.label]).toEqual([
            null,
            "Last hand",
        ]);
        expect(reopened.effects).toEqual([]);
        expect(playDisplay(reopened.state, NO_PLAY_UI)).toMatchObject({
            lastResult: null,
            result: { action: { label: "Standings" } },
            resultOverStandings: true,
        });
        expect(nextPlayUi(reopened.state, turned, lastResult.command).resultPage).toBeNull();
    });

    it("once a discard is sent marks the tile it played and offers nothing more", () => {
        const display = playDisplay(checkpointState("call_prompt_seat_1", "discarded"), NO_PLAY_UI);

        expect(handMarks(display).filter(([, mark]) => mark !== "waiting")).toEqual([
            [116, "selected"],
        ]);
        expect([display.tileIntents.size, display.actions, display.countdown]).toEqual([
            0,
            [],
            null,
        ]);
    });
});

describe("playDisplay decisions", () => {
    it("takes a chi with a choice in two steps: only the server's options, laid as they will lie, Back in Pass's place", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const choosing = nextPlayUi(state, NO_PLAY_UI, CHOOSE_CHI);
        const display = playDisplay(state, choosing);
        const [first] = display.actions;
        assert(first.command.kind === "intent");
        const sent = stepGameClient(state, {
            at: state.now,
            intent: first.command.intent,
            kind: "intent",
        });

        expect(
            display.actions.map((action) => [
                action.label,
                action.pressed,
                action.rank,
                laid(action.group),
            ]),
        ).toEqual([
            ["Chi", null, "call", ["sideways 3m", "upright 2m", "upright 4m"]],
            ["Chi", null, "call", ["sideways 3m", "upright 1m", "upright 2m"]],
            ["Chi", true, "call", null],
            ["Back", null, "pass", null],
        ]);
        expect(display.actions.slice(0, 2).map((action) => action.command)).toEqual([
            {
                intent: { offer: { kind: "chi", sequence: [4, 12], tileId: 8 }, type: "choose" },
                kind: "intent",
            },
            {
                intent: { offer: { kind: "chi", sequence: [0, 4], tileId: 8 }, type: "choose" },
                kind: "intent",
            },
        ]);
        expect(sent.effects).toEqual([{ message: buildChiAction(8, [4, 12], 1), type: "send" }]);
        expect(playDisplay(sent.state, choosing).actions.map((action) => action.chosen)).toEqual([
            true,
            false,
            false,
            false,
        ]);
    });

    it("goes back from a call's choice of tiles by Back, Escape or the call pressed again, and never into a newer wait's", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const choosing = nextPlayUi(state, NO_PLAY_UI, CHOOSE_CHI);
        const { actions, escape } = playDisplay(state, choosing);
        const older = { ...NO_PLAY_UI, tileChoice: { kind: "chi", waitId: 0 } } as const;
        assert(escape !== null);

        expect([escape, actions.at(-1)?.command]).toEqual([
            { kind: "step_back" },
            { kind: "step_back" },
        ]);
        expect(nextPlayUi(state, choosing, escape)).toEqual(NO_PLAY_UI);
        expect(nextPlayUi(state, choosing, CHOOSE_CHI)).toEqual(NO_PLAY_UI);
        expect(playDisplay(state, older).actions.map((action) => action.label)).toEqual([
            "Kan",
            "Pon",
            "Chi",
            "Pass",
        ]);
        expect(playDisplay(state, NO_PLAY_UI).escape).toBeNull();
    });

    it("offers a closed kan of either of two types as one Kan, then each kan laid with its ends face down", () => {
        const state = checkpointState("kan_choice_seat_1", "kan offer");
        const choosing = nextPlayUi(state, NO_PLAY_UI, {
            kind: "toggle_tile_choice",
            offer: "kan",
        });

        expect(
            playDisplay(state, NO_PLAY_UI).actions.map((action) => [action.label, action.pressed]),
        ).toEqual([["Kan", false]]);
        expect(
            playDisplay(state, choosing).actions.map((action) => [
                action.label,
                laid(action.group),
                action.command,
            ]),
        ).toEqual([
            [
                "Kan",
                ["facedown 1m", "upright 1m", "upright 1m", "facedown 1m"],
                {
                    intent: {
                        offer: { kanType: "closed", kind: "kan", tileId: 0 },
                        type: "choose",
                    },
                    kind: "intent",
                },
            ],
            [
                "Kan",
                ["facedown 9p", "upright 9p", "upright 9p", "facedown 9p"],
                {
                    intent: {
                        offer: { kanType: "closed", kind: "kan", tileId: 68 },
                        type: "choose",
                    },
                    kind: "intent",
                },
            ],
            ["Kan", null, { kind: "toggle_tile_choice", offer: "kan" }],
            ["Back", null, { kind: "step_back" }],
        ]);
    });

    it("keeps an answered call's controls in place, inert, marking the one that sent the answer", () => {
        const state = checkpointState("anchor_seat_1", "call offer");
        const open = playDisplay(state, NO_PLAY_UI);
        const passed = stepGameClient(state, {
            at: state.now,
            intent: { type: "pass" },
            kind: "intent",
        }).state;
        const sent = playDisplay(passed, NO_PLAY_UI);

        expect(sent.actions.map((action) => [action.label, action.chosen])).toEqual([
            ["Pon", false],
            ["Pass", true],
        ]);
        expect(sent.actions.map((action) => ({ ...action, chosen: false }))).toEqual(open.actions);
        expect([sent.decisionStanding, sent.countdown, sent.escape]).toEqual([
            "submitted",
            null,
            null,
        ]);
        expect(nextPlayUi(passed, NO_PLAY_UI, CHOOSE_CHI)).toEqual(NO_PLAY_UI);
    });

    it("marks the kan a chankan offer may rob in its meld until the offer resolves", () => {
        function sourceMelds(label: string): (number | undefined)[] {
            const { board } = playDisplay(
                checkpointState("chankan_robbed_seat_3", label),
                NO_PLAY_UI,
            );
            return (board?.players ?? []).map((player) => player.sourceMeld);
        }

        expect(sourceMelds("chankan prompt")).toEqual([undefined, undefined, 0, undefined]);
        expect(sourceMelds("ron chosen")).toEqual([undefined, undefined, 0, undefined]);
        expect(sourceMelds("round end")).toEqual([undefined, undefined, undefined, undefined]);
    });
});

function noticeTexts(state: GameClientState): string[] {
    return playDisplay(state, NO_PLAY_UI).notices.map((notice) => notice.text);
}

function playingScenario(): ReturnType<typeof clientScenario> {
    const scenario = clientScenario();
    scenario.step(clientEvent.opened(0));
    scenario.step(clientEvent.message(0, WIRE_GAME_STARTED));
    return scenario;
}

/** A playing seat that confirmed, at `at`, the round end owed by wait id 5, so a refusal can name that request. */
function confirmSentScenario(at: number): ReturnType<typeof clientScenario> {
    const scenario = playingScenario();
    scenario.step(clientEvent.message(0, wireRoundEnd(5)));
    scenario.step(clientEvent.confirm(at));
    return scenario;
}

describe("playDisplay revealed hands", () => {
    it("shows the hands a result reveals face up on the board, from its round end and a reconnect's snapshot of it", () => {
        expect(handShows(checkpointState("double_ron_seat_1", "round end"))).toEqual([
            "face",
            "concealed",
            "face",
            "concealed",
        ]);
        expect(handShows(checkpointState("double_ron_seat_1", "reconnected"))).toEqual([
            "face",
            "concealed",
            "face",
            "concealed",
        ]);
    });
});

describe("playDisplay notices", () => {
    it("shows a dropped connection until the snapshot, then that the seat is back for 3 s", () => {
        const scenario = playingScenario();
        const shown: string[][] = [];
        for (const event of [
            clientEvent.closed(100, 1006),
            clientEvent.tick(1100),
            clientEvent.opened(1200),
            clientEvent.message(1300, WIRE_GAME_RECONNECTED),
            clientEvent.tick(4299),
            clientEvent.tick(4300),
        ]) {
            scenario.step(event);
            shown.push(noticeTexts(scenario.state));
        }

        const lost = ["Connection lost. Reconnecting…"];
        expect(shown).toEqual([lost, lost, lost, ["Reconnected"], ["Reconnected"], []]);
    });

    it("replaces that the seat is back with the loss when the socket drops again within its 3 s", () => {
        const scenario = playingScenario();
        scenario.step(clientEvent.closed(100, 1006));
        scenario.step(clientEvent.tick(1100));
        scenario.step(clientEvent.opened(1200));
        scenario.step(clientEvent.message(1300, WIRE_GAME_RECONNECTED));

        scenario.step(clientEvent.closed(2000, 1006));

        expect(noticeTexts(scenario.state)).toEqual(["Connection lost. Reconnecting…"]);
    });

    it("shows no loss and no return when a page only resumes its seat, as after a reload", () => {
        const scenario = clientScenario();
        const shown: string[][] = [];
        for (const event of [
            clientEvent.opened(100),
            clientEvent.message(200, wireSessionError("join_game_already_started")),
            clientEvent.message(300, WIRE_GAME_RECONNECTED),
        ]) {
            scenario.step(event);
            shown.push(noticeTexts(scenario.state));
        }

        expect(shown).toEqual([[], [], []]);
    });

    it("says the game cannot be reached from the first failed connect, steadily across the retries", () => {
        const scenario = clientScenario();
        const shown: string[][] = [noticeTexts(scenario.state)];
        for (const event of [
            clientEvent.tick(10_000),
            clientEvent.tick(11_000),
            clientEvent.closed(11_500, 1006),
            clientEvent.tick(13_500),
            clientEvent.opened(13_600),
        ]) {
            scenario.step(event);
            shown.push(noticeTexts(scenario.state));
        }

        const unreachable = ["Cannot reach the game. Retrying…"];
        expect(shown).toEqual([[], ...Array.from({ length: 5 }, () => unreachable)]);
    });

    it("shows a refused move or a rate-limited one of the sent request until it expires, but never a stale one", () => {
        const scenario = confirmSentScenario(2000);

        scenario.step(clientEvent.message(2100, wireGameError("stale_action", 5)));
        expect(noticeTexts(scenario.state)).toEqual([]);
        scenario.step(clientEvent.message(2200, wireGameError("invalid_action", 5)));
        expect([noticeTexts(scenario.state), nextDeadline(scenario.state)]).toEqual([
            ["That move was refused"],
            6200,
        ]);
        scenario.step(clientEvent.confirm(2250));
        scenario.step(clientEvent.message(2300, wireSessionError("rate_limited", 5)));
        expect(noticeTexts(scenario.state)).toEqual(["Too fast. Try that again"]);
        scenario.step(clientEvent.tick(6300));
        expect([noticeTexts(scenario.state), nextDeadline(scenario.state)]).toEqual([[], null]);
    });

    it("keeps a server message it cannot read on the board until a reconnect's snapshot rebuilds the table", () => {
        const scenario = playingScenario();

        scenario.step(clientEvent.message(100, { t: 999 }));
        scenario.step(clientEvent.message(200, { t: 999 }));
        expect(noticeTexts(scenario.state)).toEqual([
            "2 server messages could not be read; the table may be wrong",
        ]);
        scenario.step(clientEvent.closed(300, 1006));
        scenario.step(clientEvent.tick(1300));
        scenario.step(clientEvent.opened(1400));
        scenario.step(clientEvent.message(1500, WIRE_GAME_RECONNECTED));

        expect(noticeTexts(scenario.state)).toEqual(["Reconnected"]);
    });

    it("blocks the board with why a kick ended the session, dropping its notices, and leaves without asking", () => {
        const scenario = confirmSentScenario(50);
        scenario.step(clientEvent.message(100, wireGameError("invalid_action", 5)));
        expect(noticeTexts(scenario.state)).toEqual(["That move was refused"]);

        scenario.step(clientEvent.closed(200, 1008));
        const display = playDisplay(scenario.state, { ...NO_PLAY_UI, confirmingLeave: true });

        expect(display.failure).toEqual({
            detail: "The server ended your session after a move it could not accept.",
            reload: false,
            title: "Removed from the game",
        });
        expect(display.notices).toEqual([]);
        expect(display.leave).toEqual({
            command: { intent: { type: "leave" }, kind: "intent" },
            confirming: false,
        });
    });
});

function plates(display: PlayDisplay): string[] {
    return (display.board?.nameplates ?? []).map(
        (plate) =>
            `${plate.name} ${plate.wind}${plate.isDealer ? " dealer" : ""}${plate.isCurrent ? " turn" : ""}` +
            `${plate.isRiichi ? " riichi" : ""} ${plate.score}${plate.aiMark === null ? "" : ` [${plate.aiMark.tag}]`}`,
    );
}

const AI_PLAYER = "[AI]";

describe("playDisplay nameplates", () => {
    it("marks the AI players the game seated, and another player's seat while an AI holds it for them", () => {
        const dealt = playDisplay(checkpointState("seat_left_seat_1", "first draw"), NO_PLAY_UI);
        expect(plates(dealt)).toEqual([
            "Alice S turn 25000",
            `Tsumogiri 2 W 25000 ${AI_PLAYER}`,
            "Bob N 25000",
            `Tsumogiri 1 E dealer 25000 ${AI_PLAYER}`,
        ]);
        const left = playDisplay(checkpointState("seat_left_seat_1", "player left"), NO_PLAY_UI);
        expect(plates(left)[2]).toBe("Bob N 25000 [Away]");
    });

    it("keeps a seat held for its player marked through the viewer's own reconnect, then clears it when they return", () => {
        const snapshot = playDisplay(
            checkpointState("seat_left_seat_1", "reconnected"),
            NO_PLAY_UI,
        );
        expect(plates(snapshot)[2]).toBe("Bob N 25000 [Away]");
        const back = playDisplay(checkpointState("seat_left_seat_1", "player back"), NO_PLAY_UI);
        expect(plates(back).slice(1)).toEqual([
            `Tsumogiri 2 W 25000 ${AI_PLAYER}`,
            "Bob N 25000",
            `Tsumogiri 1 E dealer 25000 ${AI_PLAYER}`,
        ]);
    });

    it("rebuilds every plate from a reconnect's snapshot, its riichi and deposit included, from the viewer's seat", () => {
        const riichi = playDisplay(
            checkpointState("riichi_reconnect_seat_1", "reconnected"),
            NO_PLAY_UI,
        );
        expect(plates(riichi)).toEqual([
            "Alice S riichi 24000",
            `Tsumogiri 2 W turn 25000 ${AI_PLAYER}`,
            `Tsumogiri 3 N 25000 ${AI_PLAYER}`,
            `Tsumogiri 1 E dealer 25000 ${AI_PLAYER}`,
        ]);
        const returned = playDisplay(
            checkpointState("seat_left_seat_3", "reconnected"),
            NO_PLAY_UI,
        );
        expect(plates(returned)).toEqual([
            "Bob N 25000",
            `Tsumogiri 1 E dealer 25000 ${AI_PLAYER}`,
            "Alice S turn 25000",
            `Tsumogiri 2 W 25000 ${AI_PLAYER}`,
        ]);
    });
});

describe("playDisplay leave", () => {
    it("asks before leaving a held seat, and the player can take the question back", () => {
        const { state } = playingScenario();
        const asked = nextPlayUi(state, NO_PLAY_UI, { kind: "ask_leave" });

        expect(playDisplay(state, NO_PLAY_UI).leave).toEqual({
            command: { kind: "ask_leave" },
            confirming: false,
        });
        expect(playDisplay(state, asked).leave.confirming).toBe(true);
        expect(nextPlayUi(state, asked, { kind: "cancel_leave" })).toEqual(NO_PLAY_UI);
    });
});

describe("playDisplay failure", () => {
    it("tells a seat taken over by another connection from a refused resume, offering a reload only where it helps", () => {
        const failures = [
            clientEvent.closed(100, 4002),
            clientEvent.message(100, wireSessionError("reconnect_already_active")),
            clientEvent.message(100, wireSessionError("reconnect_no_session")),
        ].map((event) => {
            const scenario = playingScenario();
            scenario.step(event);
            const { failure } = playDisplay(scenario.state, NO_PLAY_UI);
            return [failure?.title, failure?.reload];
        });

        expect(failures).toEqual([
            ["Opened elsewhere", false],
            ["Session error", true],
            ["Game unavailable", true],
        ]);
    });
});

describe("playDisplay callouts", () => {
    function calloutsAt(name: string, label: string): PlayDisplay["callouts"] {
        return playDisplay(checkpointState(name, label), NO_PLAY_UI).callouts;
    }

    it("calls the viewer's chi by its seat for a while, then drops it once its time ran out", () => {
        const turn = checkpointState("call_prompt_seat_1", "turn");
        const later = stepGameClient(turn, { at: turn.now + CALLOUT_MS, kind: "tick" }).state;

        expect(playDisplay(turn, NO_PLAY_UI).callouts).toEqual({
            items: [{ kind: "chi", label: "Chi", position: "bottom" }],
            key: "call-5000",
        });
        expect(nextDeadline(turn)).toBe(turn.now + CALLOUT_MS);
        expect(playDisplay(later, NO_PLAY_UI).callouts).toBeNull();
    });

    it("keeps a call through the viewer's draw that follows it at once, and shows each win's call by its winner", () => {
        expect(calloutsAt("own_turn_seat_1", "rinshan")?.items).toEqual([
            { kind: "kan", label: "Kan", position: "bottom" },
        ]);
        expect(calloutsAt("own_turn_seat_1", "ron prompt")?.items).toEqual([
            { kind: "riichi", label: "Riichi", position: "bottom" },
        ]);
        expect(calloutsAt("double_ron_seat_1", "round end")?.items).toEqual([
            { kind: "ron", label: "Ron", position: "bottom" },
            { kind: "ron", label: "Ron", position: "top" },
        ]);
    });

    it("calls a kan open to chankan once: not again for the prompt a reconnect re-sends, nor as nobody robs it", () => {
        function callsAt(label: string): GameClientState["calls"] {
            return checkpointState("chankan_passed_seat_3", label).calls;
        }
        const kan = { at: 8000, calls: [{ kanTileType: 14, kind: "kan", seat: 1 }], until: 9500 };

        expect(calloutsAt("chankan_passed_seat_3", "chankan prompt")?.items).toEqual([
            { kind: "kan", label: "Kan", position: "top" },
        ]);
        expect(callsAt("chankan prompt")).toEqual(kan);
        expect(callsAt("prompt re-sent")).toEqual(kan);
        expect(callsAt("kan")).toBeNull();
    });

    it("calls each of two kans one seat declares in quick succession", () => {
        const dealt = checkpointState("call_prompt_seat_1", "dealt");
        function closedKan(tileType: number): Record<string, unknown> {
            return { m: (CLOSED_KAN_OFFSET + tileType) * 4 + 2, t: 0 };
        }
        const first = stepGameClient(dealt, {
            at: 3100,
            kind: "server_message",
            raw: closedKan(33),
        }).state;
        const second = stepGameClient(first, {
            at: 3600,
            kind: "server_message",
            raw: closedKan(32),
        }).state;

        expect(second.calls).toEqual({
            at: 3600,
            calls: [{ kanTileType: 32, kind: "kan", seat: 2 }],
            until: 3600 + CALLOUT_MS,
        });
        expect(playDisplay(second, NO_PLAY_UI).callouts?.key).not.toBe(
            playDisplay(first, NO_PLAY_UI).callouts?.key,
        );
    });
});
