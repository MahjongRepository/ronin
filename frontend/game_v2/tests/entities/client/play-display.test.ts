import { assert, describe, expect, it } from "vitest";

import { clientEvent, clientScenario } from "#tests/fixtures/scenario";
import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    wireGameError,
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
import { type HandTile } from "@/entities/tile";

const KUIKAE_BLOCKED = [9, 10, 11];

/** The viewer's hand on the board as `[tileId, mark]`, the drawn tile last, an unmarked tile as "idle". */
function handMarks(display: PlayDisplay): [number | undefined, string][] {
    const bottom = display.board?.players[0];
    const tiles: HandTile[] = [
        ...(bottom?.hand ?? []),
        ...(bottom?.drawnTile ? [bottom.drawnTile] : []),
    ];
    return tiles.map((tile) => [tile.tileId, tile.state ?? "idle"]);
}

/** The state once logical time reaches the open decision's deadline, which shows it as expired. */
function pastDeadline(state: GameClientState): GameClientState {
    const at = state.decision?.deadline ?? Number.NaN;
    return stepGameClient(state, { at, kind: "tick" }).state;
}

function viewerTiles(state: GameClientState): readonly number[] {
    return state.table.players.find((player) => player.seat === state.viewerSeat)?.tiles ?? [];
}

describe("playDisplay", () => {
    it("shows a call prompt as its offers, in the server's order, then Pass, still once expired, and no tile plays", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const display = playDisplay(state, NO_PLAY_UI);
        const expired = playDisplay(pastDeadline(state), NO_PLAY_UI);

        expect(display.actions.map((action) => [action.label, action.tiles])).toEqual([
            ["Kan", ["3m"]],
            ["Pon", ["3m"]],
            ["Chi", ["2m", "4m"]],
            ["Chi", ["1m", "2m"]],
            ["Pass", []],
        ]);
        expect(display.actions[2].command).toEqual({
            intent: { offer: { kind: "chi", sequence: [4, 12], tileId: 8 }, type: "choose" },
            kind: "intent",
        });
        expect(display.countdown).toEqual({ kind: "running", move: "call", secondsLeft: 5 });
        expect(display.tileIntents.size).toBe(0);
        expect(handMarks(display).every(([, mark]) => mark === "waiting")).toBe(true);
        expect(expired.actions).toEqual(display.actions);
        expect(expired.countdown).toEqual({ kind: "expired", move: "call" });
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
        expect([display.tileAction, display.actions[0].pressed]).toEqual([
            "Declare riichi discarding",
            true,
        ]);
        expect(nextPlayUi(state, picking, toggle)).toEqual(NO_PLAY_UI);
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
            countdown: { kind: "running", move: "result", secondsLeft: 20 },
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
            countdown: { kind: "running", move: "result", secondsLeft: 9 },
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

function noticeTexts(state: GameClientState): string[] {
    return playDisplay(state, NO_PLAY_UI).notices.map((notice) => notice.text);
}

function playingScenario(): ReturnType<typeof clientScenario> {
    const scenario = clientScenario();
    scenario.step(clientEvent.opened(0));
    scenario.step(clientEvent.message(0, WIRE_GAME_STARTED));
    return scenario;
}

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

    it("shows a refused move or a rate-limited one until it expires, but never a stale one", () => {
        const scenario = playingScenario();

        scenario.step(clientEvent.message(100, wireGameError("stale_action")));
        expect(noticeTexts(scenario.state)).toEqual([]);
        scenario.step(clientEvent.message(200, wireGameError("invalid_discard")));
        expect([noticeTexts(scenario.state), nextDeadline(scenario.state)]).toEqual([
            ["That move was refused"],
            4200,
        ]);
        scenario.step(clientEvent.message(300, wireSessionError("rate_limited")));
        expect(noticeTexts(scenario.state)).toEqual(["Too fast. Try that again"]);
        scenario.step(clientEvent.tick(4300));
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
        const scenario = playingScenario();
        scenario.step(clientEvent.message(100, wireGameError("invalid_discard")));

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

    it("clears the AI mark of a player who comes back after the viewer's own reconnect saw an AI in their seat", () => {
        const snapshot = playDisplay(
            checkpointState("seat_left_seat_1", "reconnected"),
            NO_PLAY_UI,
        );
        expect(plates(snapshot)[2]).toBe(`Bob N 25000 ${AI_PLAYER}`);
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
