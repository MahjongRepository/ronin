import { describe, expect, it } from "vitest";

import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    type GameClientState,
    NO_PLAY_UI,
    type PlayDisplay,
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
