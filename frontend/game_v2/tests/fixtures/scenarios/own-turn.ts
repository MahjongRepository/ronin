import { type SeatScenario } from "@/entities/client";
import {
    KAN_TYPE,
    NUM_TILES,
    PLAYER_ACTION,
    SEAT_TILE_SPACE,
    buildDiscardAction,
    buildJoinGameMessage,
    buildKanAction,
    buildRiichiAction,
} from "@/shared/protocol";

const GAME_ID = "own-turn-game";
const HANDOFF = { gameTicket: "ticket-alice", wsUrl: `ws://game/ws/${GAME_ID}` } as const;
const TIMER = { bk: 20, gp: 3, mb: 60, md: 5, ra: 10, rb: 10, tb: 5 } as const;
const PLAYERS = [
    { ai: 0, nm: "Alice", s: 0 },
    { ai: 1, nm: "Bob", s: 1 },
    { ai: 1, nm: "Charlie", s: 2 },
    { ai: 1, nm: "Diana", s: 3 },
] as const;
const SCORES = [0, 1, 2, 3].map((seat) => ({ s: seat, sc: 250 }));

/** Alice deals herself all four East winds (108-111), so her first draw offers a closed kan of type 27. */
const ALICE_HAND = [0, 4, 8, 36, 40, 44, 72, 76, 80, 108, 109, 110, 111] as const;
const EAST = 108;
const EAST_TYPE = 27;
const CLOSED_KAN_OF_EAST = 24_396;
const FIRST_DRAW = 84;
const RINSHAN_DRAW = 88;
const RIICHI_TURN_DRAW = 92;
const TSUMOGIRI_RIICHI_FLAGS = 3;

/** A discard's packed wire value: its flags, then its seat and tile. */
function packedDiscard(seat: number, tileId: number, flags = 0): number {
    return flags * SEAT_TILE_SPACE + seat * NUM_TILES + tileId;
}

/**
 * Alice (seat 0, the dealer) draws into a closed kan, which she declares; the rinshan draw offers riichi, which she
 * declares on it. The other seats each discard a tile they drew unseen, and on her next turn, in riichi, only her
 * drawn tile goes: another tile sends nothing.
 */
export const OWN_TURN_SCENARIO: SeatScenario = {
    gameId: GAME_ID,
    handoff: HANDOFF,
    name: "own turn: closed kan, rinshan, riichi",
    seat: 0,
    startAt: 0,
    startEffects: [{ type: "open_socket", url: HANDOFF.wsUrl }],
    steps: [
        {
            effects: [{ message: buildJoinGameMessage(HANDOFF.gameTicket), type: "send" }],
            event: { at: 0, kind: "transport_opened" },
        },
        {
            event: {
                at: 10,
                kind: "server_message",
                raw: {
                    dd: [
                        [1, 2],
                        [3, 4],
                    ],
                    dl: 0,
                    gid: GAME_ID,
                    gt: 0,
                    p: PLAYERS,
                    s: 0,
                    t: 8,
                    tm: TIMER,
                },
            },
        },
        {
            event: {
                at: 3010,
                kind: "server_message",
                raw: {
                    cp: 0,
                    dc: [3, 4],
                    di: [52],
                    dl: 0,
                    h: 0,
                    mt: ALICE_HAND,
                    n: 0,
                    p: SCORES,
                    r: 0,
                    s: 0,
                    t: 9,
                    w: 0,
                },
            },
        },
        {
            event: {
                at: 3100,
                kind: "server_message",
                raw: {
                    aa: [
                        { a: PLAYER_ACTION.RIICHI, tl: [FIRST_DRAW, 0] },
                        { a: PLAYER_ACTION.KAN, tl: [EAST_TYPE] },
                    ],
                    bk: 20,
                    d: FIRST_DRAW,
                    el: 2,
                    t: 1,
                    wi: 1,
                },
            },
            label: "turn",
        },
        {
            effects: [{ message: buildKanAction(EAST, KAN_TYPE.CLOSED, 1), type: "send" }],
            event: {
                at: 3500,
                intent: {
                    offer: { kanType: KAN_TYPE.CLOSED, kind: "kan", tileId: EAST },
                    type: "choose",
                },
                kind: "intent",
            },
            label: "kan chosen",
        },
        {
            event: { at: 3600, kind: "server_message", raw: { m: CLOSED_KAN_OF_EAST, t: 0 } },
        },
        { event: { at: 3610, kind: "server_message", raw: { t: 6, ti: 2 } } },
        {
            event: {
                at: 3620,
                kind: "server_message",
                raw: {
                    aa: [{ a: PLAYER_ACTION.RIICHI, tl: [RINSHAN_DRAW] }],
                    bk: 20,
                    d: RINSHAN_DRAW,
                    t: 1,
                    wi: 2,
                },
            },
            label: "rinshan",
        },
        {
            effects: [{ message: buildRiichiAction(RINSHAN_DRAW, 2), type: "send" }],
            event: {
                at: 4000,
                intent: { offer: { kind: "riichi", tileId: RINSHAN_DRAW }, type: "choose" },
                kind: "intent",
            },
            label: "riichi chosen",
        },
        {
            event: {
                at: 4100,
                kind: "server_message",
                raw: { d: packedDiscard(0, RINSHAN_DRAW, TSUMOGIRI_RIICHI_FLAGS), t: 2 },
            },
        },
        { event: { at: 4110, kind: "server_message", raw: { s: 0, t: 5 } } },
        {
            event: { at: 4200, kind: "server_message", raw: { d: packedDiscard(1, 120), t: 2 } },
        },
        {
            event: { at: 4300, kind: "server_message", raw: { d: packedDiscard(2, 124), t: 2 } },
        },
        {
            event: { at: 4400, kind: "server_message", raw: { d: packedDiscard(3, 128), t: 2 } },
        },
        {
            event: {
                at: 4500,
                kind: "server_message",
                raw: { bk: 18, d: RIICHI_TURN_DRAW, t: 1, wi: 3 },
            },
            label: "riichi turn",
        },
        {
            event: { at: 4600, intent: { tileId: 0, type: "discard" }, kind: "intent" },
            label: "not the drawn tile",
        },
        {
            effects: [{ message: buildDiscardAction(RIICHI_TURN_DRAW, 3), type: "send" }],
            event: {
                at: 4700,
                intent: { tileId: RIICHI_TURN_DRAW, type: "discard" },
                kind: "intent",
            },
            label: "tsumogiri",
        },
    ],
};
