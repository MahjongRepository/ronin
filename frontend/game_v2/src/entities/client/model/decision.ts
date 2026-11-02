import { DesyncError, type GamePhase, type PlayerState, ponOfType } from "@/entities/table";
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
    tileType,
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
 * What each message does to the wait a decision answers, so a new message type must say: it closes when the server
 * moved on to a draw (the viewer's, or another seat's notice of one), a discard, a meld, the next prompt or turn, or out
 * of the round. A dora reveal, a riichi stick, a seat control or furiten notice, an error and a session message keep it.
 */
const DECISION_AFTER: Readonly<Record<ParsedServerMessage["type"], "close" | "keep">> = {
    ai_replacement: "keep",
    call_prompt: "close",
    discard: "close",
    dora_revealed: "keep",
    draw: "close",
    draw_notice: "close",
    error: "keep",
    furiten: "keep",
    game_end: "close",
    game_joined: "keep",
    game_reconnected: "close",
    game_started: "close",
    human_return: "keep",
    meld: "close",
    riichi_declared: "keep",
    round_end: "close",
    round_started: "close",
    session_error: "keep",
    turn: "close",
};

/**
 * What opening a decision reads besides its message: when it opens, the table's phase, the timer settings, the
 * viewer's known hand and its melds.
 */
export interface DecisionContext {
    readonly at: number;
    readonly phase: GamePhase;
    readonly timer: TimerSettings | null;
    readonly viewerSeat: number | null;
    readonly hand: readonly number[];
    readonly melds: PlayerState["melds"];
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

/**
 * A turn's offers from the draw's available actions; a kan names a tile type, answered with a tile of it. A kan of a
 * type the hand holds no tile of, or an added kan of a type the seat has no pon of, means the hand the client holds is
 * not the server's.
 */
function actionOffers(
    action: AvailableAction,
    { hand, melds }: Pick<DecisionContext, "hand" | "melds">,
): Offer[] {
    function kanOffer(kanType: KanType, type: number): Offer {
        const tileId = hand.find((handTile) => tileType(handTile) === type);
        if (tileId === undefined) {
            throw new DesyncError(`A kan of tile type ${type} is offered, but the hand holds none`);
        }
        if (kanType === KAN_TYPE.ADDED && ponOfType(melds, type) === undefined) {
            throw new DesyncError(
                `An added kan of tile type ${type} is offered, but the seat has no pon of it`,
            );
        }
        return { kanType, kind: "kan", tileId };
    }
    switch (action.action) {
        case PLAYER_ACTION.RIICHI: {
            return [...new Set(action.tileIds)].map((tileId) => ({ kind: "riichi", tileId }));
        }
        case PLAYER_ACTION.TSUMO: {
            return [{ kind: "tsumo" }];
        }
        case PLAYER_ACTION.KAN: {
            return action.tileTypes.map((type) => kanOffer(KAN_TYPE.CLOSED, type));
        }
        case PLAYER_ACTION.ADDED_KAN: {
            return action.tileTypes.map((type) => kanOffer(KAN_TYPE.ADDED, type));
        }
        case PLAYER_ACTION.KYUUSHU: {
            return [{ kind: "kyuushu" }];
        }
        default: {
            return assertNever(action);
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
                return call.options.map((sequence) => ({ kind: "chi", sequence, tileId }));
            }
            case MELD_CALL_TYPE.OPEN_KAN: {
                return [{ kanType: KAN_TYPE.OPEN, kind: "kan", tileId }];
            }
            default: {
                return assertNever(call);
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
    const opened: Pick<TurnDecision, "offers" | "opening"> =
        event.type === "draw"
            ? {
                  offers: event.availableActions.flatMap((action) => actionOffers(action, context)),
                  opening: { drawnTileId: event.tileId, kind: "draw" },
              }
            : {
                  offers: [],
                  opening: { kind: "after_call", kuikaeTileTypes: event.kuikaeTileTypes },
              };
    return {
        ...turnDeadlines(context.timer, context.at, event),
        ...opened,
        kind: "turn",
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
 * a call prompt its call. Only a message that carries a wait id opens one, so a replay never does. An offer of a code
 * or shape the client does not know never parses; one it cannot resolve against the hand (a kan of a type the hand
 * lacks, an added kan with no pon) throws a `DesyncError` rather than being dropped, as does an opening outside a
 * round (a `turn` before the deal, a prompt after the round end), which no table event guards.
 */
export function openDecision(
    message: ParsedServerMessage,
    context: DecisionContext,
): Decision | null {
    const opened = openedBy(message, context);
    if (opened !== null && context.phase !== "in_round") {
        throw new DesyncError(`A ${message.type} opens a decision on a ${context.phase} table`);
    }
    return opened;
}

function openedBy(message: ParsedServerMessage, context: DecisionContext): Decision | null {
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

/** A refusal of one of the client's requests: the server's code and the wait id the refused request echoed. */
export interface Refusal {
    readonly code: string;
    readonly waitId: number;
}

/**
 * The refusal a message makes of a request whose wait may go on, or null: the game refused it (but as stale, since a
 * stale answer's wait already ended), or the socket's rate limit dropped it before it reached the game. Either names
 * the refused frame's own wait id; one that names none (a rate limit of a frame without a readable id) answers no
 * request, so it is null too.
 */
export function refusalOf(message: ParsedServerMessage): Refusal | null {
    const refuses =
        (message.type === "error" && message.code !== GAME_ERROR_CODE.STALE_ACTION) ||
        (message.type === "session_error" && message.code === SESSION_ERROR_CODE.RATE_LIMITED);
    if (!refuses || message.waitId === null) {
        return null;
    }
    return { code: message.code, waitId: message.waitId };
}

/**
 * Whether a message only repeats the wait a decision already answered: a snapshot naming its wait id, or that wait's
 * opening re-sent after it. A resync request that went unanswered past its due time is sent again, so a late second
 * snapshot can follow the player's answer to the first one's wait; the answer is on its way, and the server judges it.
 */
export function isAnsweredWait(decision: Decision, message: ParsedServerMessage): boolean {
    if (decision.status.kind !== "submitted") {
        return false;
    }
    const repeats =
        message.type === "game_reconnected" ||
        message.type === "draw" ||
        message.type === "turn" ||
        message.type === "call_prompt";
    return repeats && message.waitId === decision.waitId;
}

/**
 * The decision after a message that opens none: closed when the server moved on; reopened for another answer
 * when the server refused the submitted one by its wait id and still waits; otherwise as it was, so a refusal of an
 * older request, or of one it cannot name, reopens nothing.
 */
export function followDecision(decision: Decision, message: ParsedServerMessage): Decision | null {
    if (DECISION_AFTER[message.type] === "close") {
        return null;
    }
    const reopened =
        decision.status.kind === "submitted" && refusalOf(message)?.waitId === decision.waitId;
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

/** Whether two intents give a decision the same answer: the same offer chosen, the same tile discarded, or a pass. */
export function sameIntent(first: DecisionIntent, second: DecisionIntent): boolean {
    switch (first.type) {
        case "choose": {
            return second.type === "choose" && offerKey(first.offer) === offerKey(second.offer);
        }
        case "discard": {
            return second.type === "discard" && first.tileId === second.tileId;
        }
        case "pass": {
            return second.type === "pass";
        }
        default: {
            return assertNever(first);
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
function takesDiscard({ opening }: TurnDecision, player: PlayerState, tileId: number): boolean {
    const kuikae =
        opening.kind === "after_call" && opening.kuikaeTileTypes.includes(tileType(tileId));
    if (!player.tiles.includes(tileId) || kuikae) {
        return false;
    }
    return !player.isRiichi || tileId === player.drawnTileId;
}

/**
 * The action `intent` gives a decision as its answer, answered already or not, or null when the decision does not
 * offer it: a choice the server did not offer, a discard on a call prompt, a pass on a turn.
 */
export function offerAnswer(
    decision: Decision,
    intent: DecisionIntent,
    viewer: PlayerState | undefined,
): ClientMessage | null {
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

/**
 * The action that answers a decision with `intent`, or null when it was already answered or does not offer it. A
 * decision past its deadline still takes one answer, which the server accepts or refuses as stale.
 */
export function answerDecision(
    decision: Decision,
    intent: DecisionIntent,
    viewer: PlayerState | undefined,
): ClientMessage | null {
    return decision.status.kind === "submitted" ? null : offerAnswer(decision, intent, viewer);
}
