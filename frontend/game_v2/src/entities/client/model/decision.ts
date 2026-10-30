import { type PlayerState } from "@/entities/table";
import { assertNever } from "@/shared/lib";
import {
    CALL_TYPE,
    type CallPromptEvent,
    type ClientMessage,
    type DrawEvent,
    GAME_ERROR_CODE,
    KAN_TYPE,
    type KanType,
    MELD_CALL_TYPE,
    PLAYER_ACTION,
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    type TimerSettings,
    type TurnEvent,
    buildChiAction,
    buildDiscardAction,
    buildKanAction,
    buildKyuushuAction,
    buildPassAction,
    buildPonAction,
    buildRiichiAction,
    buildRonAction,
    buildTsumoAction,
} from "@/shared/protocol";

import {
    type CallDecision,
    type Decision,
    type DecisionIntent,
    type Offer,
    type TurnDecision,
} from "./types";

const MS_PER_SECOND = 1000;
const OPEN = { kind: "open" } as const;

type AvailableAction = DrawEvent["availableActions"][number];

/**
 * Messages that end the wait a decision answers: the server moved on to a draw, a discard, a meld, the next prompt
 * or turn, or out of the round. A dora reveal, a riichi stick, a furiten notice, an error and a session message do
 * not.
 */
const CLOSING_TYPES: ReadonlySet<ParsedServerMessage["type"]> = new Set([
    "call_prompt",
    "discard",
    "draw",
    "game_end",
    "game_reconnected",
    "game_started",
    "meld",
    "round_end",
    "round_started",
    "turn",
]);

/** What opening a decision reads besides its message: when it opens, the timer settings, the viewer's known hand. */
export interface DecisionContext {
    readonly at: number;
    readonly timer: TimerSettings | null;
    readonly viewerSeat: number | null;
    readonly hand: readonly number[];
}

function tileType(tileId: number): number {
    return Math.floor(tileId / 4);
}

/** When a wait's server timer runs out: `seconds` from its opening, less what a re-sent wait says has run. */
function deadlineAfter(at: number, seconds: number, elapsedSeconds: number | null): number {
    return at + Math.max(0, seconds - (elapsedSeconds ?? 0)) * MS_PER_SECOND;
}

const UNTIMED_TURN = { baseDeadline: null, deadline: null } as const;

/**
 * A turn runs its base time, then the bank its opening message names, which drains only once the base ran out; a
 * re-sent wait's elapsed time comes off the base first. The client keeps no bank of its own, so a turn message without
 * one gets no deadline rather than a guess.
 */
function turnDeadlines(
    timer: TimerSettings | null,
    at: number,
    event: DrawEvent | TurnEvent,
): Pick<TurnDecision, "baseDeadline" | "deadline"> {
    if (timer === null || event.bankSeconds === null) {
        return UNTIMED_TURN;
    }
    const { baseTurnSeconds } = timer;
    return {
        baseDeadline: deadlineAfter(at, baseTurnSeconds, event.elapsedSeconds),
        deadline: deadlineAfter(at, baseTurnSeconds + event.bankSeconds, event.elapsedSeconds),
    };
}

function kanOffer(kanType: KanType, tileId: number | undefined): Offer[] {
    return tileId === undefined ? [] : [{ kanType, kind: "kan", tileId }];
}

/** A turn's offers from the draw's available actions; a kan names a tile type, answered with a tile of it. */
function actionOffers(action: AvailableAction, hand: readonly number[]): Offer[] {
    const tiles = action.tiles ?? [];
    function handTileOf(type: number): number | undefined {
        return hand.find((tileId) => tileType(tileId) === type);
    }
    switch (action.action) {
        case PLAYER_ACTION.RIICHI: {
            return [...new Set(tiles)].map((tileId) => ({ kind: "riichi", tileId }));
        }
        case PLAYER_ACTION.TSUMO: {
            return [{ kind: "tsumo" }];
        }
        case PLAYER_ACTION.KAN: {
            return tiles.flatMap((type) => kanOffer(KAN_TYPE.CLOSED, handTileOf(type)));
        }
        case PLAYER_ACTION.ADDED_KAN: {
            return tiles.flatMap((type) => kanOffer(KAN_TYPE.ADDED, handTileOf(type)));
        }
        case PLAYER_ACTION.KYUUSHU: {
            return [{ kind: "kyuushu" }];
        }
        default: {
            return [];
        }
    }
}

function promptOffers(prompt: CallPromptEvent): Offer[] {
    const ron: Offer[] = prompt.callType === CALL_TYPE.MELD ? [] : [{ kind: "ron" }];
    if (prompt.callType === CALL_TYPE.CHANKAN) {
        return ron;
    }
    const { tileId } = prompt;
    const melds = prompt.availableCalls.flatMap((call): Offer[] => {
        switch (call.callType) {
            case MELD_CALL_TYPE.PON: {
                return [{ kind: "pon", tileId }];
            }
            case MELD_CALL_TYPE.CHI: {
                return (call.options ?? []).map((sequence) => ({ kind: "chi", sequence, tileId }));
            }
            case MELD_CALL_TYPE.OPEN_KAN: {
                return [{ kanType: KAN_TYPE.OPEN, kind: "kan", tileId }];
            }
            default: {
                return assertNever(call.callType);
            }
        }
    });
    return [...ron, ...melds];
}

function openTurn(
    event: DrawEvent | TurnEvent,
    waitId: number,
    context: DecisionContext,
): TurnDecision {
    const offers =
        event.type === "draw"
            ? event.availableActions.flatMap((action) => actionOffers(action, context.hand))
            : [];
    return {
        ...turnDeadlines(context.timer, context.at, event),
        drawnTileId: event.type === "draw" ? event.tileId : null,
        kind: "turn",
        kuikaeTileTypes: event.type === "turn" ? event.kuikaeTileTypes : [],
        offers,
        openedAt: context.at,
        status: OPEN,
        waitId,
    };
}

function openCall(prompt: CallPromptEvent, waitId: number, context: DecisionContext): CallDecision {
    const { at, timer } = context;
    return {
        callType: prompt.callType,
        deadline:
            timer === null
                ? null
                : deadlineAfter(at, timer.meldDecisionSeconds, prompt.elapsedSeconds),
        fromSeat: prompt.fromSeat,
        kind: "call",
        offers: promptOffers(prompt),
        openedAt: at,
        status: OPEN,
        tileId: prompt.tileId,
        waitId,
    };
}

/**
 * The decision a message opens for the viewer's seat, or null: the seat's own draw or `turn` event opens its turn,
 * a call prompt its call. Only a message that carries a wait id opens one, so a replay never does.
 */
export function openDecision(
    message: ParsedServerMessage,
    context: DecisionContext,
): Decision | null {
    switch (message.type) {
        case "draw": {
            const { waitId } = message;
            const ownDraw = message.seat === context.viewerSeat && waitId !== null;
            return ownDraw ? openTurn(message, waitId, context) : null;
        }
        case "turn": {
            return message.waitId === null ? null : openTurn(message, message.waitId, context);
        }
        case "call_prompt": {
            return message.waitId === null ? null : openCall(message, message.waitId, context);
        }
        default: {
            return null;
        }
    }
}

/**
 * Whether a message refuses the submitted answer while its wait goes on: the game refused it (but as stale, since
 * a stale answer's wait already ended), or the socket's rate limit dropped it before it reached the game.
 */
export function refusesSubmission(
    message: ParsedServerMessage,
): message is Extract<ParsedServerMessage, { type: "error" | "session_error" }> {
    if (message.type === "error") {
        return message.code !== GAME_ERROR_CODE.STALE_ACTION;
    }
    return message.type === "session_error" && message.code === SESSION_ERROR_CODE.RATE_LIMITED;
}

/**
 * The decision after a message that opens none: closed when the server moved on; reopened for another answer
 * when the server refused the submitted one and still waits; otherwise as it was.
 */
export function followDecision(decision: Decision, message: ParsedServerMessage): Decision | null {
    if (CLOSING_TYPES.has(message.type)) {
        return null;
    }
    const reopened = decision.status.kind === "submitted" && refusesSubmission(message);
    return reopened ? { ...decision, status: OPEN } : decision;
}

/**
 * The decision as it stands at logical time `now`: an open one past its deadline shows as expired. That is for
 * display only: the deadline is the client's estimate of the server's timer, and the server alone decides by the
 * wait id whether an answer still counts, so an expired decision still takes one.
 */
export function expireDecision(decision: Decision, now: number): Decision {
    const due = decision.deadline !== null && now >= decision.deadline;
    return decision.status.kind === "open" && due
        ? { ...decision, status: { kind: "expired" } }
        : decision;
}

function offerKey(offer: Offer): string {
    switch (offer.kind) {
        case "tsumo":
        case "kyuushu":
        case "ron": {
            return offer.kind;
        }
        case "riichi":
        case "pon": {
            return `${offer.kind}:${offer.tileId}`;
        }
        case "kan": {
            return `kan:${offer.kanType}:${offer.tileId}`;
        }
        case "chi": {
            return `chi:${offer.tileId}:${offer.sequence.join(",")}`;
        }
        default: {
            return assertNever(offer);
        }
    }
}

function offerMessage(offer: Offer, waitId: number): ClientMessage {
    switch (offer.kind) {
        case "tsumo": {
            return buildTsumoAction(waitId);
        }
        case "riichi": {
            return buildRiichiAction(offer.tileId, waitId);
        }
        case "kan": {
            return buildKanAction(offer.tileId, offer.kanType, waitId);
        }
        case "kyuushu": {
            return buildKyuushuAction(waitId);
        }
        case "ron": {
            return buildRonAction(waitId);
        }
        case "pon": {
            return buildPonAction(offer.tileId, waitId);
        }
        case "chi": {
            const [first, second] = offer.sequence;
            return buildChiAction(offer.tileId, [first, second], waitId);
        }
        default: {
            return assertNever(offer);
        }
    }
}

/**
 * Whether the turn takes a discard of `tileId`, the one rule the client applies itself: any tile in hand but the
 * types kuikae blocks, and in riichi only the drawn tile.
 */
function takesDiscard(decision: TurnDecision, player: PlayerState, tileId: number): boolean {
    if (!player.tiles.includes(tileId) || decision.kuikaeTileTypes.includes(tileType(tileId))) {
        return false;
    }
    return !player.isRiichi || tileId === player.drawnTileId;
}

/**
 * The action that answers a decision with `intent`, or null when it was already answered or does not take it: a
 * choice the server did not offer, a discard on a call prompt, a pass on a turn. A decision past its deadline still
 * takes one answer, which the server accepts or refuses as stale; the client never answers without the player's
 * instruction, standing (a play switch) or given.
 */
export function answerDecision(
    decision: Decision,
    intent: DecisionIntent,
    viewer: PlayerState | undefined,
): ClientMessage | null {
    if (decision.status.kind === "submitted") {
        return null;
    }
    switch (intent.type) {
        case "choose": {
            const key = offerKey(intent.offer);
            const offered = decision.offers.some((offer) => offerKey(offer) === key);
            return offered ? offerMessage(intent.offer, decision.waitId) : null;
        }
        case "pass": {
            return decision.kind === "call" ? buildPassAction(decision.waitId) : null;
        }
        case "discard": {
            const takes =
                decision.kind === "turn" &&
                viewer !== undefined &&
                takesDiscard(decision, viewer, intent.tileId);
            return takes ? buildDiscardAction(intent.tileId, decision.waitId) : null;
        }
        default: {
            return assertNever(intent);
        }
    }
}
