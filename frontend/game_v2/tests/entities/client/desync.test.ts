import { render } from "lit-html";
import { assert, describe, expect, it } from "vitest";

import { GAME_ID, HANDOFF, clientEvent } from "#tests/fixtures/scenario";
import {
    checkpointState,
    loadSeatScenario,
    receivedPayload,
} from "#tests/fixtures/seat-transcripts";
import {
    WIRE_GAME_JOINED,
    WIRE_GAME_STARTED,
    WIRE_ROUND_STARTED,
    type WirePayload,
    wireNumberList,
    wirePayloadList,
    wirePayloadOf,
    wireSessionError,
} from "#tests/fixtures/wire";
import {
    type ClientEffect,
    type DesyncCause,
    type LiveClient,
    type LiveEvent,
    MAX_RESYNC_REQUESTS,
    RESYNC_ANSWER_MS,
    decisionOf,
    desyncOf,
    nextDeadline,
    roundConfirmOf,
    serverSilenceLimitMs,
    startGameClient,
    stepGameClient,
} from "@/entities/client";
import { boardOverlay } from "@/entities/table";
import { standingsDisplay } from "@/entities/table/lib/standings-display";
import {
    EVENT_TYPE,
    NUM_TILES,
    PLAYER_ACTION,
    SESSION_ERROR_CODE,
    buildDiscardAction,
    buildReconnectMessage,
    buildResyncMessage,
} from "@/shared/protocol";

const { closed, message, opened, tick } = clientEvent;

const SCENARIO = "own_turn_seat_1";
const { transcript } = loadSeatScenario(SCENARIO);
const SNAPSHOT = receivedPayload(transcript, "reconnected");
const RESENT_DRAW = receivedPayload(transcript, "draw re-sent");
const TURN_WAIT_ID = 1;
const RESYNC: ClientEffect = { message: buildResyncMessage(), type: "send" };
const AT = 3100;

/** The seat's turn as the transcript opened it, its draw at 3000, playing on an open socket. */
function onTurn(): LiveClient {
    return checkpointState(SCENARIO, "first draw");
}

function viewerTiles(state: LiveClient): readonly number[] {
    return state.table.players.find((player) => player.seat === state.viewerSeat)?.tiles ?? [];
}

/** A discard by the viewer's seat of a tile its hand, known whole, does not hold: a table step that throws. */
function impossibleDiscard(state: LiveClient): WirePayload {
    const seat = state.viewerSeat ?? 0;
    const tileId = [...Array.from({ length: NUM_TILES }).keys()].find(
        (candidate) => !viewerTiles(state).includes(candidate),
    );
    return { d: seat * NUM_TILES + (tileId ?? 0), t: EVENT_TYPE.DISCARD };
}

/** The viewer's own draw offering a closed kan of a tile type the hand holds none of, beside the drawn tile's. */
function unmatchedKanDraw(state: LiveClient): WirePayload {
    const seat = state.viewerSeat ?? 0;
    const held = new Set(viewerTiles(state).map((tileId) => Math.floor(tileId / 4)));
    const absentType =
        [...Array.from({ length: NUM_TILES / 4 }).keys()].find((type) => !held.has(type)) ?? 0;
    const drawnTile = viewerTiles(state).at(0) ?? 0;
    return {
        aa: [{ a: PLAYER_ACTION.KAN, tl: [absentType] }],
        bk: 30,
        d: seat * NUM_TILES + drawnTile,
        t: EVENT_TYPE.DRAW,
        wi: TURN_WAIT_ID + 1,
    };
}

/** The viewer's own draw offering an added kan of a tile type the hand holds but the seat has no pon of. */
function ponlessAddedKanDraw(state: LiveClient): WirePayload {
    const seat = state.viewerSeat ?? 0;
    const drawnTile = viewerTiles(state).at(0) ?? 0;
    return {
        aa: [{ a: PLAYER_ACTION.ADDED_KAN, tl: [Math.floor(drawnTile / 4)] }],
        bk: 30,
        d: seat * NUM_TILES + drawnTile,
        t: EVENT_TYPE.DRAW,
        wi: TURN_WAIT_ID + 1,
    };
}

interface FailureCase {
    readonly name: string;
    readonly cause: DesyncCause;
    readonly detail: string;
    readonly event: (state: LiveClient) => LiveEvent;
}

const FAILURES: readonly FailureCase[] = [
    {
        cause: "unreadable_message",
        detail: "Unknown game event type",
        event: () => message(AT, { t: 999 }),
        name: "a message that does not parse",
    },
    {
        cause: "undecodable_frame",
        detail: "non-binary",
        event: () => ({ at: AT, detail: "Received a non-binary frame", kind: "frame_undecodable" }),
        name: "a frame that does not decode",
    },
    {
        cause: "impossible_state",
        detail: "not found in hand",
        event: (state) => message(AT, impossibleDiscard(state)),
        name: "a table step that throws",
    },
    {
        cause: "impossible_state",
        detail: "but the hand holds none",
        event: (state) => message(AT, unmatchedKanDraw(state)),
        name: "an offer the hand holds no tile for",
    },
    {
        cause: "impossible_state",
        detail: "but the seat has no pon of it",
        event: (state) => message(AT, ponlessAddedKanDraw(state)),
        name: "an added kan with no pon to add to",
    },
];

const SNAPSHOT_SEATS = wirePayloadList(SNAPSHOT, "pst");
const OWN_TILES = wireNumberList(SNAPSHOT, "mt");
const PENDING_SNAPSHOT = receivedPayload(
    loadSeatScenario("chankan_robbed_seat_1").transcript,
    "reconnected",
);
const PENDING_RESULT = wirePayloadOf(PENDING_SNAPSHOT, "re");

/** The snapshot with one seat's state left out, the others as the server sent them. */
function withoutSeatState(seat: number): WirePayload {
    return { ...SNAPSHOT, pst: SNAPSHOT_SEATS.filter((state) => state.s !== seat) };
}

/** The snapshot with seat 2's melds replaced by `melds`. */
function withSeat2Melds(melds: readonly number[]): WirePayload {
    return {
        ...SNAPSHOT,
        pst: SNAPSHOT_SEATS.map((state) => (state.s === 2 ? { ...state, ml: melds } : state)),
    };
}

const INCOMPLETE_SNAPSHOTS: readonly { name: string; payload: WirePayload }[] = [
    { name: "that does not parse", payload: { ...SNAPSHOT, mt: "not tiles" } },
    { name: "missing a seat's state", payload: withoutSeatState(2) },
    { name: "with no players", payload: { ...SNAPSHOT, p: [] } },
    {
        name: "listing a seat's state twice",
        payload: { ...SNAPSHOT, pst: SNAPSHOT_SEATS.map((state) => ({ ...state, s: 0 })) },
    },
    { name: "with a meld that does not decode", payload: withSeat2Melds([-1]) },
    { name: "with another seat's meld", payload: withSeat2Melds([6080]) },
    { name: "whose history misses a finished round", payload: { ...SNAPSHOT, n: 1 } },
    { name: "whose own hand misses a tile", payload: { ...SNAPSHOT, mt: OWN_TILES.slice(1) } },
    {
        name: "whose own hand holds a tile twice",
        payload: { ...SNAPSHOT, mt: [OWN_TILES[1], ...OWN_TILES.slice(1)] },
    },
    {
        name: "whose seat holds a count no turn leaves",
        payload: {
            ...SNAPSHOT,
            pst: SNAPSHOT_SEATS.map((state) => (state.s === 2 ? { ...state, tc: 12 } : state)),
        },
    },
    {
        name: "whose pending result misses a seat's score",
        payload: { ...PENDING_SNAPSHOT, re: { ...PENDING_RESULT, scs: { "0": 250, "2": 250 } } },
    },
];

/** Step `events` from `state`, returning the state after them and every effect they asked for. */
function run(
    state: LiveClient,
    events: readonly LiveEvent[],
): { state: LiveClient; effects: ClientEffect[] } {
    let current = state;
    const effects: ClientEffect[] = [];
    for (const event of events) {
        const step = stepGameClient(current, event);
        current = step.state;
        effects.push(...step.effects);
    }
    return { effects, state: current };
}

function socketError(at: number): LiveEvent {
    return { at, detail: "", kind: "transport_error" };
}

function sends(effects: readonly ClientEffect[]): ClientEffect[] {
    return effects.filter((effect) => effect.type === "send" || effect.type === "close_socket");
}

function discardIntent(at: number, tileId: number): LiveEvent {
    return { at, intent: { tileId, type: "discard" }, kind: "intent" };
}

const DOUBLE_RON_END = receivedPayload(
    loadSeatScenario("double_ron_seat_1").transcript,
    "round end",
);
const [firstWinner, ...otherWinners] = wirePayloadList(DOUBLE_RON_END, "wn");

const DROPPED_AT = 4000;
const OPENED_AT = 5001;
const LOST_AT = 5002;
const RECONNECT: ClientEffect = { message: buildReconnectMessage("ticket-1"), type: "send" };

function undecodable(at: number): LiveEvent {
    return { at, detail: "Received a non-binary frame", kind: "frame_undecodable" };
}

function drawNotice(at: number): LiveEvent {
    return message(at, { s: 2, t: EVENT_TYPE.DRAW_NOTICE });
}

/** The first draw's socket dropped and reopened, the RECONNECT sent and its snapshot frame undecodable. */
function lostWhileIdentifying(): LiveClient {
    const reopened = run(onTurn(), [
        closed(DROPPED_AT, 1006),
        tick(OPENED_AT - 1),
        opened(OPENED_AT),
    ]);
    expect(sends(reopened.effects)).toEqual([RECONNECT]);
    return run(reopened.state, [undecodable(LOST_AT), drawNotice(6000)]).state;
}

describe("stepGameClient - desync", () => {
    it.each(FAILURES)(
        "puts the client out of step on $name: it reports it, asks once for a snapshot and answers nothing",
        ({ cause, detail, event }) => {
            const turn = onTurn();
            const [tile] = viewerTiles(turn);

            const failed = stepGameClient(turn, event(turn));
            expect(failed.effects.map((effect) => effect.type)).toEqual([
                "report_protocol_failure",
                "send",
            ]);
            expect(failed.effects[1]).toEqual(RESYNC);
            expect(desyncOf(failed.state)).toMatchObject({
                cause,
                detail: expect.stringContaining(detail),
                request: { due: AT + RESYNC_ANSWER_MS, kind: "sent" },
                since: AT,
            });
            expect([
                decisionOf(failed.state),
                failed.state.resyncRequests,
                desyncOf(failed.state)?.unreadMessages ?? 0,
            ]).toEqual([null, 1, 1]);
            expect(stepGameClient(failed.state, discardIntent(AT + 10, tile)).effects).toEqual([]);
            expect(failed.state.session).toBe(turn.session);
        },
    );

    it("drops a delta while out of step, leaving the table it lost step on", () => {
        const desynced = run(onTurn(), [message(AT, { t: 999 })]).state;

        const dropped = run(desynced, [message(AT + 50, { s: 2, t: EVENT_TYPE.DRAW_NOTICE })]);
        expect(dropped.effects).toEqual([]);
        expect(dropped.state.table).toBe(desynced.table);
        expect(desyncOf(dropped.state)).toBe(desyncOf(desynced));
    });

    it("takes the snapshot and the re-sent wait, back in step, and answers again, its seen wait kept", () => {
        const desynced = run(onTurn(), [message(AT, { t: 999 })]).state;

        const resynced = run(desynced, [
            message(AT + 100, SNAPSHOT),
            message(AT + 100, RESENT_DRAW),
        ]);
        expect(resynced.effects).toEqual([]);
        expect(desyncOf(resynced.state)).toBeNull();
        expect(decisionOf(resynced.state)).toMatchObject({
            kind: "turn",
            status: { kind: "open" },
            waitId: TURN_WAIT_ID,
        });
        expect(resynced.state.highestOpenedWaitId).toBe(TURN_WAIT_ID);
        const [tile] = viewerTiles(resynced.state);
        expect(stepGameClient(resynced.state, discardIntent(AT + 200, tile)).effects).toEqual([
            { message: buildDiscardAction(tile, TURN_WAIT_ID), type: "send" },
        ]);
    });

    it.each(INCOMPLETE_SNAPSHOTS)(
        "ends the page as failed, still out of step and closing its socket, on a snapshot $name",
        ({ payload }) => {
            const desynced = run(onTurn(), [message(AT, { t: 999 })]).state;

            const failed = run(desynced, [message(AT + 100, payload)]);
            expect(sends(failed.effects)).toEqual([{ type: "close_socket" }]);
            expect(failed.state.session).toMatchObject({
                reason: { kind: "failed" },
                status: "ended",
            });
            expect(desyncOf(failed.state)).toMatchObject({
                cause: "unreadable_message",
                since: AT,
            });
            expect(failed.state.table).toBe(desynced.table);
            expect(nextDeadline(failed.state)).toBeNull();
        },
    );

    it("records a loss of step when the snapshot that ends the page came while it was in step", () => {
        const failed = run(onTurn(), [message(AT, withoutSeatState(2))]);

        expect(failed.state.session).toMatchObject({ reason: { kind: "failed" } });
        expect(desyncOf(failed.state)).toMatchObject({ cause: "unreadable_message", since: AT });
        expect(failed.state.table.roundHistoryInStep).toBe(false);
    });

    it.each([
        {
            name: "a winner's meld does not decode",
            payload: { ...DOUBLE_RON_END, wn: [{ ...firstWinner, ml: [-1] }, ...otherWinners] },
        },
        {
            name: "a seat's score is missing",
            payload: { ...DOUBLE_RON_END, scs: { "0": 250, "1": 250, "3": 250 } },
        },
    ])(
        "puts the client out of step on a round end where $name, opening no confirm",
        ({ payload }) => {
            const lost = run(checkpointState("double_ron_seat_1", "ron chosen"), [
                message(5500, payload),
            ]);
            expect(desyncOf(lost.state)).toMatchObject({ cause: "unreadable_message" });
            expect([roundConfirmOf(lost.state), lost.state.table.phase]).toEqual([
                null,
                "in_round",
            ]);
        },
    );

    it("asks again when its request goes unanswered past its due time", () => {
        const desynced = run(onTurn(), [message(AT, { t: 999 })]).state;
        const due = AT + RESYNC_ANSWER_MS;
        expect(nextDeadline(desynced)).toBeLessThanOrEqual(due);

        const early = run(desynced, [tick(due - 1)]);
        expect(sends(early.effects)).toEqual([]);
        const late = run(early.state, [tick(due)]);
        expect(sends(late.effects)).toEqual([RESYNC]);
        expect([late.state.resyncRequests, desyncOf(late.state)?.request]).toEqual([
            2,
            { due: due + RESYNC_ANSWER_MS, kind: "sent" },
        ]);
    });

    it("ends the page once it lost step more often than its budget, however many snapshots rebuilt it", () => {
        let state = onTurn();
        for (let attempt = 1; attempt <= MAX_RESYNC_REQUESTS; attempt += 1) {
            const at = AT + attempt * 1000;
            const recovered = run(state, [message(at, { t: 999 }), message(at + 100, SNAPSHOT)]);
            expect(sends(recovered.effects)).toEqual([RESYNC]);
            expect(desyncOf(recovered.state)).toBeNull();
            ({ state } = recovered);
        }

        const failed = run(state, [message(AT + 10_000, { t: 999 })]);
        expect(sends(failed.effects)).toEqual([{ type: "close_socket" }]);
        expect(failed.state.session).toMatchObject({ reason: { kind: "failed" }, status: "ended" });
    });

    it("forgets its request when the socket drops, the reconnect's snapshot rebuilding it with no request more", () => {
        const desynced = run(onTurn(), [message(AT, { t: 999 })]).state;

        const dropped = run(desynced, [closed(AT + 100, 1006)]);
        expect(desyncOf(dropped.state)?.request).toEqual({ kind: "unsent" });
        const retryAt = nextDeadline(dropped.state) ?? 0;
        const reconnected = run(dropped.state, [
            tick(retryAt),
            opened(retryAt),
            message(retryAt, SNAPSHOT),
        ]);
        expect(sends(reconnected.effects)).toEqual([
            { message: buildReconnectMessage("ticket-1"), type: "send" },
        ]);
        expect([desyncOf(reconnected.state), reconnected.state.resyncRequests]).toEqual([null, 1]);
        expect(reconnected.state.session).toMatchObject({ status: "playing" });
    });
});

describe("stepGameClient - a game's end its table refuses in step", () => {
    it("ends on the server's standings when the game's end is the first sign of a missed round end, sending nothing", () => {
        const final = loadSeatScenario("final_round_seat_1").transcript;
        const gameEnd = message(5000, receivedPayload(final, "game end"));

        const ended = run(checkpointState("final_round_seat_1", "ron chosen"), [gameEnd]);
        const { session, table } = ended.state;
        const standings = standingsDisplay(table, ended.state.viewerSeat);
        expect(session).toMatchObject({ reason: { kind: "game_ended" }, status: "ended" });
        expect([
            table.phase,
            table.gameEndResult?.standings.length,
            table.roundEndResult,
            roundConfirmOf(ended.state),
            sends(ended.effects),
            standings?.ledgerComplete,
        ]).toEqual(["game_ended", 4, null, null, [], false]);
    });
});

describe("stepGameClient - desync around the game's start and end", () => {
    const FINAL = "final_round_seat_1";
    const finalRound = loadSeatScenario(FINAL).transcript;
    const finalRoundEnd = receivedPayload(finalRound, "round end");
    const gameEnd = receivedPayload(finalRound, "game end");

    function ledgerOf(state: LiveClient): { rows: number; complete: boolean } {
        const display = standingsDisplay(state.table, state.viewerSeat);
        return { complete: display?.ledgerComplete ?? false, rows: display?.ledger.length ?? -1 };
    }

    /** The note the last result's panel, shown over the standings, gives when its details may be wrong, or null. */
    function resultNote(state: LiveClient): string | null {
        const host = document.createElement("div");
        render(boardOverlay(state.table, { paging: { overStandings: true, page: 0 } }), host);
        expect(host.querySelector(".round-end-result")).not.toBeNull();
        return host.querySelector(".round-end-result__uncertain")?.getAttribute("role") ?? null;
    }

    it("ends on the server's last result and standings out of step, its ledger and result marked uncertain", () => {
        const inStep = checkpointState(FINAL, "game end");
        expect([ledgerOf(inStep), resultNote(inStep)]).toEqual([{ complete: true, rows: 1 }, null]);
        const desynced = run(checkpointState(FINAL, "ron chosen"), [
            message(5000, { t: 999 }),
        ]).state;

        const ended = run(desynced, [message(5000, finalRoundEnd), message(5000, gameEnd)]);
        expect(ended.state.session).toMatchObject({
            reason: { kind: "game_ended" },
            status: "ended",
        });
        expect([ended.state.table.phase, ended.state.showsLastResult]).toEqual([
            "game_ended",
            true,
        ]);
        expect([ledgerOf(ended.state), resultNote(ended.state)]).toEqual([
            { complete: false, rows: 1 },
            "note",
        ]);
    });

    it("never shows an earlier hand's result as the last one when the page lost step after it", () => {
        const RECONNECT_GAME = "game_end_reconnect_seat_1";
        const reconnectGame = loadSeatScenario(RECONNECT_GAME).transcript;
        const earlier = checkpointState(RECONNECT_GAME, "kyuushu round end");
        expect(earlier.table.roundEndResult).not.toBeNull();

        const ended = run(earlier, [
            message(5100, { t: 999 }),
            message(5200, { ...receivedPayload(reconnectGame, "last round end"), rt: 99 }),
            message(5200, receivedPayload(reconnectGame, "game end")),
        ]);
        expect(ended.state.session).toMatchObject({ reason: { kind: "game_ended" } });
        expect([ended.state.table.roundEndResult, ended.state.showsLastResult]).toEqual([
            null,
            false,
        ]);
        expect(ledgerOf(ended.state).complete).toBe(false);
    });

    it("marks the ledger incomplete when the last round end itself could not be read, the leftover sticks the server's", () => {
        const lost = run(checkpointState(FINAL, "ron chosen"), [message(5000, { t: 999 })]).state;
        const desynced = { ...lost, table: { ...lost.table, riichiSticks: 2 } };

        const ended = run(desynced, [
            message(5000, { ...finalRoundEnd, rt: 99 }),
            message(5000, gameEnd),
        ]);
        expect(ended.state.session).toMatchObject({
            reason: { kind: "game_ended" },
            status: "ended",
        });
        expect([ended.state.table.phase, ended.state.table.roundEndResult]).toEqual([
            "game_ended",
            null,
        ]);
        expect(ledgerOf(ended.state)).toEqual({ complete: false, rows: 0 });
        expect(gameEnd.lr).toBe(0);
        expect(standingsDisplay(ended.state.table, ended.state.viewerSeat)?.leftover).toBeNull();
    });

    it("asks again when the first deal is due once the server says the game has not dealt yet", () => {
        const started = checkpointState(SCENARIO, "game started");
        const desynced = run(started, [message(100, { t: 999 })]);
        expect(sends(desynced.effects)).toEqual([RESYNC]);
        const firstDealDue = started.firstDealDue ?? 0;

        const refused = run(desynced.state, [
            message(120, wireSessionError(SESSION_ERROR_CODE.GAME_NOT_STARTED)),
        ]);
        expect([refused.effects, desyncOf(refused.state)?.request]).toEqual([
            [],
            { due: firstDealDue, kind: "at_deal" },
        ]);
        const dealDue = run(refused.state, [tick(firstDealDue)]);
        expect(sends(dealDue.effects)).toEqual([RESYNC]);
    });
});

/** A joined seat out of step before the game started, its resync request refused as the game has not dealt. */
function refusedBeforeDeal(): { state: LiveClient; effects: ClientEffect[] } {
    return run(startGameClient(GAME_ID, HANDOFF, 0).state, [
        opened(0),
        message(0, WIRE_GAME_JOINED),
        message(100, { t: 999 }),
        message(120, wireSessionError(SESSION_ERROR_CODE.GAME_NOT_STARTED)),
    ]);
}

describe("stepGameClient - desync before the first deal", () => {
    it("asks again only once the game moves when the server says it has not dealt and no deal time is known, so a long wait spends no requests", () => {
        const refused = refusedBeforeDeal();
        const waited = run(refused.state, [socketError(60_000), tick(120_000)]);
        const started = run(waited.state, [
            message(120_000, receivedPayload(transcript, "game started")),
        ]);
        const firstDealDue = started.state.firstDealDue ?? 0;
        const dealt = run(started.state, [tick(firstDealDue)]);
        const moved = run(waited.state, [message(120_000, WIRE_ROUND_STARTED)]);

        expect(sends(refused.effects).slice(1)).toEqual([RESYNC]);
        expect([waited.effects, nextDeadline(waited.state), sends(started.effects)]).toEqual([
            [],
            null,
            [],
        ]);
        expect([sends(dealt.effects), sends(moved.effects), firstDealDue > 120_000]).toEqual([
            [RESYNC],
            [RESYNC],
            true,
        ]);
        expect(dealt.state.resyncRequests).toBe(2);
    });

    it("keeps a game start's timer settings while awaiting the deal, so the socket waits through a long start pause", () => {
        const timer = { bk: 20, gp: 240, mb: 60, md: 10, ra: 15, rb: 5, tb: 5 };
        const started = run(refusedBeforeDeal().state, [
            message(500, { ...WIRE_GAME_STARTED, s: 0, tm: timer }),
        ]);

        expect([started.state.firstDealDue, nextDeadline(started.state)]).toEqual([
            240_500, 240_500,
        ]);
        expect(serverSilenceLimitMs(started.state)).toBe(265_000);
    });

    it("forgets the answered request with the socket, so a rate limit of the reopened socket's JOIN retries the identity", () => {
        const reopened = run(refusedBeforeDeal().state, [
            closed(500, 1006),
            tick(1500),
            opened(1501),
        ]);
        const limited = run(reopened.state, [
            message(1502, wireSessionError(SESSION_ERROR_CODE.RATE_LIMITED)),
        ]);

        const { session } = limited.state;
        assert(session.status === "identifying");

        expect(desyncOf(reopened.state)?.request.kind).toBe("awaiting_snapshot");
        expect(session.sessionRetryAt).toBeGreaterThan(1502);
        expect(sends(limited.effects)).toEqual([]);
    });
});

describe("stepGameClient - a late second snapshot", () => {
    it("replaces an expired decision the player left unanswered when its wait is opened again, timed afresh from the server's elapsed time", () => {
        const resentAt = AT + 100;
        const resynced = run(onTurn(), [
            message(AT, { t: 999 }),
            message(resentAt, SNAPSHOT),
            message(resentAt, RESENT_DRAW),
        ]).state;
        const first = decisionOf(resynced);
        assert(first?.kind === "turn" && first.deadline !== null && first.baseDeadline !== null);
        const expired = run(resynced, [tick(first.deadline)]).state;
        const shift = first.deadline + 500 - resentAt;
        const reopened = run(expired, [message(resentAt + shift, RESENT_DRAW)]);

        expect(decisionOf(expired)?.status.kind).toBe("expired");
        expect([reopened.effects, decisionOf(reopened.state)]).toEqual([
            [],
            {
                ...first,
                baseDeadline: first.baseDeadline + shift,
                deadline: first.deadline + shift,
                openedAt: resentAt + shift,
            },
        ]);
    });

    it("keeps the answer the player sent to the first snapshot's wait when a second repeats it", () => {
        const desynced = run(onTurn(), [message(AT, { t: 999 })]).state;
        const askedTwice = run(desynced, [tick(AT + RESYNC_ANSWER_MS)]);
        expect(sends(askedTwice.effects)).toEqual([RESYNC]);
        const first = run(askedTwice.state, [
            message(AT + 10_100, SNAPSHOT),
            message(AT + 10_100, RESENT_DRAW),
        ]).state;
        const [tile] = viewerTiles(first);
        const answered = run(first, [discardIntent(AT + 10_200, tile)]);
        expect(sends(answered.effects)).toEqual([
            { message: buildDiscardAction(tile, TURN_WAIT_ID), type: "send" },
        ]);

        const repeated = run(answered.state, [
            message(AT + 10_300, SNAPSHOT),
            message(AT + 10_300, RESENT_DRAW),
            discardIntent(AT + 10_400, tile),
        ]);
        expect(repeated.effects).toEqual([]);
        expect(decisionOf(repeated.state)?.status).toMatchObject({ kind: "submitted" });
    });
});

describe("stepGameClient - out of step while the reconnect identifies", () => {
    it("asks for a snapshot on the open socket once the reconnect's own goes unanswered, and is admitted by it", () => {
        const lost = lostWhileIdentifying();
        expect([lost.session?.status, desyncOf(lost)?.cause]).toEqual([
            "identifying",
            "undecodable_frame",
        ]);
        const due = LOST_AT + RESYNC_ANSWER_MS;
        expect(nextDeadline(lost)).toBe(due);

        const asked = run(lost, [tick(due - 1), tick(due)]);
        expect(sends(asked.effects)).toEqual([RESYNC]);
        const admitted = run(asked.state, [
            message(due + 100, SNAPSHOT),
            message(due + 100, RESENT_DRAW),
        ]);
        expect([admitted.state.session?.status, desyncOf(admitted.state)]).toEqual([
            "playing",
            null,
        ]);
        expect(decisionOf(admitted.state)).toMatchObject({ status: { kind: "open" } });
    });

    it("ends the page once its requests are spent on answers that never decode, whatever deltas arrive", () => {
        let state = lostWhileIdentifying();
        for (let request = 1; request <= MAX_RESYNC_REQUESTS; request += 1) {
            const due = nextDeadline(state) ?? 0;
            const asked = run(state, [tick(due), undecodable(due + 10), drawNotice(due + 20)]);
            expect(sends(asked.effects)).toEqual([RESYNC]);
            ({ state } = asked);
        }

        const spent = run(state, [tick(nextDeadline(state) ?? 0)]);
        expect(sends(spent.effects)).toEqual([{ type: "close_socket" }]);
        expect(spent.state.session).toMatchObject({ reason: { kind: "failed" }, status: "ended" });
        expect(nextDeadline(spent.state)).toBeNull();
    });

    it("resends the identity message when the server says the reopened socket holds no seat", () => {
        const lost = lostWhileIdentifying();
        const due = LOST_AT + RESYNC_ANSWER_MS;
        const refused = run(lost, [
            tick(due),
            message(due + 10, wireSessionError(SESSION_ERROR_CODE.NOT_IN_GAME)),
        ]);
        expect(refused.state.session).toMatchObject({ status: "identifying" });

        const resent = run(refused.state, [tick(nextDeadline(refused.state) ?? 0)]);
        expect(sends(resent.effects)).toEqual([RECONNECT]);
        const admitted = run(resent.state, [message(due + 2000, SNAPSHOT)]);
        expect([admitted.state.session?.status, desyncOf(admitted.state)]).toEqual([
            "playing",
            null,
        ]);
    });

    it("takes a rate limit while its request is outstanding as the request's, asking again when it comes due and never resending the identity", () => {
        const lost = lostWhileIdentifying();
        const due = LOST_AT + RESYNC_ANSWER_MS;
        const asked = run(lost, [tick(due)]);
        expect(sends(asked.effects)).toEqual([RESYNC]);

        const limited = run(asked.state, [
            message(due + 1, wireSessionError(SESSION_ERROR_CODE.RATE_LIMITED)),
        ]);
        expect([limited.effects, limited.state.session]).toEqual([[], asked.state.session]);
        const later = run(limited.state, [
            tick(due + 1001),
            tick(due + RESYNC_ANSWER_MS - 1),
            tick(due + RESYNC_ANSWER_MS),
        ]);
        expect(sends(later.effects)).toEqual([RESYNC]);
    });

    it("asks nothing while a session retry waits, then gives the resent identity's snapshot its time", () => {
        const lost = lostWhileIdentifying();
        const due = LOST_AT + RESYNC_ANSWER_MS;
        const later = run(lost, [
            message(due - 1, wireSessionError(SESSION_ERROR_CODE.RECONNECT_RETRY_LATER)),
        ]).state;
        const retryAt = nextDeadline(later) ?? 0;
        expect(retryAt).toBeGreaterThan(due);

        const waiting = run(later, [tick(due), tick(retryAt - 1)]);
        expect(sends(waiting.effects)).toEqual([]);
        const resent = run(waiting.state, [tick(retryAt)]);
        expect([sends(resent.effects), resent.state.resyncRequests]).toEqual([[RECONNECT], 0]);
        expect(nextDeadline(resent.state)).toBe(retryAt + RESYNC_ANSWER_MS);
    });
});
