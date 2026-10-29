import { type SeatScenario } from "@/entities/client";
import {
    NUM_TILES,
    buildDiscardAction,
    buildJoinGameMessage,
    buildPassAction,
    buildPonAction,
    buildReconnectMessage,
} from "@/shared/protocol";

const HANDOFF = { gameTicket: "ticket-bob", wsUrl: "ws://game/ws/prompt-game" } as const;
const TIMER = { bk: 20, gp: 3, mb: 60, md: 5, ra: 10, rb: 10, tb: 5 } as const;
const PLAYERS = [
    { ai: 0, nm: "Alice", s: 0 },
    { ai: 0, nm: "Bob", s: 1 },
    { ai: 1, nm: "Charlie", s: 2 },
    { ai: 1, nm: "Diana", s: 3 },
] as const;
const DEALER_DICE = [
    [1, 2],
    [3, 4],
] as const;
const BOB_HAND = [4, 8, 24, 28, 32, 34, 35, 44, 48, 65, 66, 72, 76] as const;
const SCORES = [0, 1, 2, 3].map((seat) => ({ s: seat, sc: 250 }));

/**
 * Bob's hand holds three 9m (32, 34, 35) and 7m 8m (24, 28), so Alice's 9m (33) offers him a pon, a kan and a
 * chi; and two 8p (65, 66), so Charlie's 8p (64) offers him a pon.
 */
const NINE_MAN = 33;
const PROMPT_WAIT = 4;
const TURN_WAIT = 5;
const PON_PASS_WAIT = 6;
const EIGHT_PIN = 64;
const PON_BY_BOB_FROM_ALICE = 17_409;

const CALL_PROMPT = {
    ac: [{ clt: 0 }, { clt: 2 }, { clt: 1, opt: [[24, 28]] }],
    clt: 1,
    cs: 1,
    frs: 0,
    t: 3,
    ti: NINE_MAN,
    wi: PROMPT_WAIT,
};

/** A plain discard's packed wire value: its seat and tile. */
function packedDiscard(seat: number, tileId: number): number {
    return seat * NUM_TILES + tileId;
}

const SNAPSHOT_SEAT = { dsc: [], ml: [], ri: false, sc: 250, tc: 13 };

/**
 * Bob (seat 1) joins, is dealt, and gets a call prompt on Alice's first discard. His socket drops before he answers,
 * a drop the server never sees, so it keeps his seat and the wait: his reconnect takes the half-open connection
 * over, the snapshot rebuilds the table, and the server re-sends the prompt with the time its timer ran. Only such
 * a takeover re-sends a wait; a seat the server saw leave gets an AI player, which answers at once
 * (`manager.py` `_send_wait_on_reconnect`). He calls pon,
 * the meld follows, and his turn after it opens with the `turn` event: kuikae keeps his last 9m in hand, so he
 * discards another tile. He passes the pon Charlie's 8p offers him, and Diana's discard moves the game on.
 */
export const CALL_PROMPT_SCENARIO: SeatScenario = {
    gameId: "prompt-game",
    handoff: HANDOFF,
    name: "call prompt across a reconnect",
    seat: 1,
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
                    dd: DEALER_DICE,
                    dl: 0,
                    gid: "prompt-game",
                    gt: 0,
                    p: PLAYERS,
                    s: 1,
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
                    mt: BOB_HAND,
                    n: 0,
                    p: SCORES,
                    r: 0,
                    s: 1,
                    t: 9,
                    w: 0,
                },
            },
            label: "dealt",
        },
        {
            event: { at: 3500, kind: "server_message", raw: { d: NINE_MAN, t: 2 } },
            label: "discarded",
        },
        {
            event: { at: 3510, kind: "server_message", raw: CALL_PROMPT },
            label: "prompt",
        },
        {
            event: { at: 4000, code: 1006, kind: "transport_closed", reason: "" },
            label: "dropped",
        },
        {
            effects: [{ type: "open_socket", url: HANDOFF.wsUrl }],
            event: { at: 5000, kind: "tick" },
        },
        {
            effects: [{ message: buildReconnectMessage(HANDOFF.gameTicket), type: "send" }],
            event: { at: 5100, kind: "transport_opened" },
        },
        {
            event: {
                at: 5200,
                kind: "server_message",
                raw: {
                    cp: 0,
                    dc: [3, 4],
                    dd: DEALER_DICE,
                    di: [52],
                    dl: 0,
                    f: false,
                    gid: "prompt-game",
                    h: 0,
                    mt: BOB_HAND,
                    n: 0,
                    p: PLAYERS,
                    pst: [
                        { ...SNAPSHOT_SEAT, dsc: [{ ti: NINE_MAN }], s: 0 },
                        { ...SNAPSHOT_SEAT, s: 1 },
                        { ...SNAPSHOT_SEAT, s: 2 },
                        { ...SNAPSHOT_SEAT, s: 3 },
                    ],
                    r: 0,
                    rh: [],
                    s: 1,
                    tm: TIMER,
                    tr: 69,
                    type: "game_reconnected",
                    w: 0,
                    wi: PROMPT_WAIT,
                },
            },
            label: "reconnected",
        },
        {
            event: { at: 5210, kind: "server_message", raw: { ...CALL_PROMPT, el: 1.7 } },
            label: "prompt re-sent",
        },
        {
            effects: [{ message: buildPonAction(NINE_MAN, PROMPT_WAIT), type: "send" }],
            event: {
                at: 6000,
                intent: { offer: { kind: "pon", tileId: NINE_MAN }, type: "choose" },
                kind: "intent",
            },
            label: "pon chosen",
        },
        {
            event: { at: 6100, kind: "server_message", raw: { m: PON_BY_BOB_FROM_ALICE, t: 0 } },
        },
        {
            event: {
                at: 6110,
                kind: "server_message",
                raw: { bk: 20, kt: [8], t: 12, wi: TURN_WAIT },
            },
            label: "turn",
        },
        {
            event: { at: 6500, intent: { tileId: 35, type: "discard" }, kind: "intent" },
            label: "kuikae discard",
        },
        {
            effects: [{ message: buildDiscardAction(4, TURN_WAIT), type: "send" }],
            event: { at: 7000, intent: { tileId: 4, type: "discard" }, kind: "intent" },
            label: "discard chosen",
        },
        { event: { at: 7100, kind: "server_message", raw: { d: packedDiscard(1, 4), t: 2 } } },
        {
            event: {
                at: 7200,
                kind: "server_message",
                raw: { d: packedDiscard(2, EIGHT_PIN), t: 2 },
            },
        },
        {
            event: {
                at: 7210,
                kind: "server_message",
                raw: {
                    ac: [{ clt: 0 }],
                    clt: 1,
                    cs: 1,
                    frs: 2,
                    t: 3,
                    ti: EIGHT_PIN,
                    wi: PON_PASS_WAIT,
                },
            },
            label: "pon prompt",
        },
        {
            effects: [{ message: buildPassAction(PON_PASS_WAIT), type: "send" }],
            event: { at: 7300, intent: { type: "pass" }, kind: "intent" },
            label: "passed",
        },
        {
            event: { at: 7400, kind: "server_message", raw: { d: packedDiscard(3, 100), t: 2 } },
            label: "moved on",
        },
    ],
};
