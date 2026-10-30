import { type EndReason, type SessionState } from "@/entities/session";
import {
    type BoardCallouts,
    type BoardDisplayState,
    type BoardNotice,
    type BoardPlayerDisplay,
    type PlayerState,
    type SeatPosition,
    type TableState,
    boardCallouts,
    roundEndPageAt,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    type HandTile,
    type PlayableState,
    type TileFace,
    type TileSpriteStatus,
    tile136toString,
} from "@/entities/tile";
import { type LoadStatus, assertNever } from "@/shared/lib";
import {
    CLIENT_MESSAGE_TYPE,
    CLOSE_CODE,
    GAME_ACTION,
    GAME_ERROR_CODE,
    SESSION_ERROR_CODE,
} from "@/shared/protocol";

import {
    type DecisionCountdown,
    decisionCountdown,
    firstDealCountdown,
    roundConfirmCountdown,
} from "./countdown";
import { takesIntent } from "./dispatch";
import {
    type Decision,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type Offer,
    type PlayIntent,
    type RoundConfirm,
    type TimedNotice,
} from "./types";

/**
 * What a control of the page does: send the client an intent, turn picking riichi's discard on or off, turn the
 * round result's panel to a page, pin a nameplate (or none) for the others' score differences, ask to leave mid-game
 * or take that back, or reload the page after a failure.
 */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" }
    | { readonly kind: "show_result_page"; readonly page: number }
    | { readonly kind: "pin_nameplate"; readonly seat: SeatPosition | null }
    | { readonly kind: "ask_leave" }
    | { readonly kind: "cancel_leave" }
    | { readonly kind: "reload" };

/** A button of the open decision: its label and the tiles that tell it from another of its kind (two chi). */
export interface PlayAction {
    readonly label: string;
    readonly tiles: readonly TileFace[];
    readonly command: PlayCommand;
    /** For a toggle, whether it is on; null for a plain button. */
    readonly pressed: boolean | null;
}

/**
 * What the view holds beside the client state: that the player is picking riichi's discard, for the decision of
 * this wait id, so a newer decision never inherits it; the page of a round's result the player turned to, for
 * the round it names, so a newer result opens on its first page while a reconnect's copy of the same one keeps it;
 * the nameplate pinned for the others' score differences, which stays pinned until the player unpins it, since the
 * viewer's seat stays at the bottom; that the player asked to leave mid-game and has yet to confirm it; and where the
 * tile sprite's load and the final standings' stand, which the page's IO owns.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
    readonly resultPage: { readonly round: string; readonly page: number } | null;
    readonly pinnedNameplate: SeatPosition | null;
    readonly confirmingLeave: boolean;
    readonly tileSprite: TileSpriteStatus;
    readonly standings: LoadStatus;
}

export const NO_PLAY_UI: PlayUi = {
    confirmingLeave: false,
    pinnedNameplate: null,
    resultPage: null,
    riichiPickWaitId: null,
    standings: "loading",
    tileSprite: "loading",
};

/** A notice over the table, with the one control it may offer. */
export interface PlayNotice extends Omit<BoardNotice, "action"> {
    readonly action?: { readonly label: string; readonly command: PlayCommand };
}

/**
 * The way back to the lobby: its command, which asks first while leaving would hand a held seat to an AI and goes
 * straight to the lobby once the session ended; and whether the player is being asked.
 */
export interface LeaveControls {
    readonly command: PlayCommand;
    readonly confirming: boolean;
}

/** An end that stopped the session on the page: why, in a player's terms, and whether reloading may help. */
export interface FailureDisplay {
    readonly title: string;
    readonly detail: string;
    readonly reload: boolean;
}

/**
 * The round result's controls in its panel: its one primary button (the next page of a result the player still has
 * to confirm, then the confirm on its last page, or the game's last result's way to the standings), whether the seat
 * waits for the others after confirming, and the countdown to the server's round advance while the confirm is owed.
 */
export interface ResultControls {
    readonly action: PlayAction | null;
    readonly waiting: boolean;
    readonly countdown: DecisionCountdown | null;
}

/**
 * The live board as the viewer plays it: the table from its seat, its own hand's tiles marked by the open decision
 * (with the intent tapping each selectable one sends), the decision's buttons, its countdown and the seat's furiten.
 */
export interface PlayDisplay {
    readonly board: BoardDisplayState | null;
    /** The calls the board shows by their seats, from the viewer's seat; null with none. */
    readonly callouts: BoardCallouts | null;
    /** The whole seconds left of the game start pause, which the seating before the first deal counts down. */
    readonly firstDealSeconds: number | null;
    readonly tileAction: string;
    readonly tileIntents: ReadonlyMap<number, LocalIntent>;
    readonly actions: readonly PlayAction[];
    readonly countdown: DecisionCountdown | null;
    /** The seat is furiten, shown only while a round plays, never under its result or the standings. */
    readonly furiten: boolean;
    /** The page of the round's result the panel shows, clamped to its pages; 0 with no result. */
    readonly resultPage: number;
    /** The nameplate pinned for the others' score differences, or null. */
    readonly pinnedNameplate: SeatPosition | null;
    /** The result panel's controls while the viewer has a round result to confirm or waits on one; else null. */
    readonly result: ResultControls | null;
    /** Whether the game's last result still shows over the standings, until the player dismisses it. */
    readonly resultOverStandings: boolean;
    /** The standings' way back to the game's last result once the player dismissed it; else null. */
    readonly lastResult: PlayAction | null;
    /** The viewer's seat, which the standings mark; null before the seat is known. */
    readonly viewerSeat: number | null;
    /** The notices over the table, the connection's first; none while a failure blocks the board. */
    readonly notices: readonly PlayNotice[];
    /** The end that blocks the board with its reason and a way back, or null. */
    readonly failure: FailureDisplay | null;
    readonly leave: LeaveControls;
}

/** How each tile of the viewer's hand plays now: its mark, and what tapping it sends when selectable. */
interface TilePlay {
    readonly state: PlayableState;
    readonly intent: DecisionIntent | null;
}

const DISCARD_ACTION = "Discard";
const RIICHI_ACTION = "Declare riichi discarding";

const OFFER_LABELS: Readonly<Record<Offer["kind"], string>> = {
    chi: "Chi",
    kan: "Kan",
    kyuushu: "Kyuushu",
    pon: "Pon",
    riichi: "Riichi",
    ron: "Ron",
    tsumo: "Tsumo",
};

const PASS: DecisionIntent = { type: "pass" };
const CONFIRM_RESULT: PlayIntent = { type: "confirm_result" };
const SHOW_LAST_RESULT: PlayIntent = { type: "show_last_result" };

const CONFIRM_LABELS: Readonly<Record<"owed" | "final", string>> = {
    final: "Standings",
    owed: "OK",
};

function choose(offer: Offer): DecisionIntent {
    return { offer, type: "choose" };
}

function intentCommand(intent: LocalIntent): PlayCommand {
    return { intent, kind: "intent" };
}

/** The tile a submitted discard or riichi played, which the hand marks while the server answers. */
function submittedTileId(decision: Decision | null): number | null {
    if (decision?.status.kind !== "submitted") {
        return null;
    }
    const { message } = decision.status;
    if (message.t !== CLIENT_MESSAGE_TYPE.GAME_ACTION) {
        return null;
    }
    const played = message.a === GAME_ACTION.DISCARD || message.a === GAME_ACTION.DECLARE_RIICHI;
    return played ? message.ti : null;
}

/** The riichi offers the client would answer now: what the riichi toggle picks from. */
function takenRiichiOffers(state: GameClientState): Offer[] {
    const offers = state.decision?.offers ?? [];
    return offers.filter((offer) => offer.kind === "riichi" && takesIntent(state, choose(offer)));
}

/** Whether the player is picking riichi's discard: toggled for this decision, which still takes a riichi. */
function pickingRiichi(state: GameClientState, ui: PlayUi): boolean {
    const { decision } = state;
    return (
        decision !== null &&
        decision.waitId === ui.riichiPickWaitId &&
        takenRiichiOffers(state).length > 0
    );
}

/** The intent a tap on `tileId` asks for: riichi with it while riichi's discard is picked, else its discard. */
function tileIntent(tileId: number, picking: boolean): DecisionIntent {
    return picking ? choose({ kind: "riichi", tileId }) : { tileId, type: "discard" };
}

/**
 * How each of the viewer's tiles plays, by asking the dispatcher whether it takes the tile's intent: selectable
 * when it does; on an open turn, disabled when it does not (kuikae, riichi, or not riichi's while picking it); the
 * tile an answer played, selected; any other moment, waiting. Every tile stays a button, so focus stays in the hand.
 */
function tilePlays(
    state: GameClientState,
    viewer: PlayerState,
    picking: boolean,
): Map<number, TilePlay> {
    const { decision } = state;
    const played = submittedTileId(decision);
    const openTurn = decision?.kind === "turn" && decision.status.kind !== "submitted";
    return new Map(
        viewer.tiles.map((tileId): [number, TilePlay] => {
            const intent = tileIntent(tileId, picking);
            if (takesIntent(state, intent)) {
                return [tileId, { intent, state: "selectable" }];
            }
            const waiting: PlayableState = openTurn ? "disabled" : "waiting";
            return [tileId, { intent: null, state: tileId === played ? "selected" : waiting }];
        }),
    );
}

function playTile(tile: HandTile, plays: ReadonlyMap<number, TilePlay>): HandTile {
    const play = tile.tileId === undefined ? undefined : plays.get(tile.tileId);
    if (play === undefined || tile.show !== "face" || tile.tileId === undefined) {
        return tile;
    }
    return { face: tile.face, show: "face", state: play.state, tileId: tile.tileId };
}

function playHand(
    player: BoardPlayerDisplay,
    plays: ReadonlyMap<number, TilePlay>,
): BoardPlayerDisplay {
    return {
        ...player,
        drawnTile: player.drawnTile === undefined ? undefined : playTile(player.drawnTile, plays),
        hand: player.hand.map((tile) => playTile(tile, plays)),
    };
}

/** The tiles that tell an offer from another of its kind: a chi's pair, the tile a pon or kan takes. */
function offerTiles(offer: Offer): TileFace[] {
    switch (offer.kind) {
        case "chi": {
            return offer.sequence.map(tile136toString);
        }
        case "pon":
        case "kan": {
            return [tile136toString(offer.tileId)];
        }
        case "tsumo":
        case "ron":
        case "kyuushu":
        case "riichi": {
            return [];
        }
        default: {
            return assertNever(offer);
        }
    }
}

function offerAction(offer: Offer): PlayAction {
    const label = OFFER_LABELS[offer.kind];
    return {
        command: intentCommand(choose(offer)),
        label,
        pressed: null,
        tiles: offerTiles(offer),
    };
}

/**
 * The open decision's buttons, each one the dispatcher would answer now: riichi first, as one toggle that picks its
 * discard from the hand, then the other offers in the order the server listed them, then a pass. An answered
 * decision takes nothing, so it shows none.
 */
function decisionActions(state: GameClientState, picking: boolean): PlayAction[] {
    const offers = state.decision?.offers ?? [];
    const riichi: PlayAction[] =
        takenRiichiOffers(state).length > 0
            ? [
                  {
                      command: { kind: "toggle_riichi_pick" },
                      label: OFFER_LABELS.riichi,
                      pressed: picking,
                      tiles: [],
                  },
              ]
            : [];
    const offered = offers
        .filter((offer) => offer.kind !== "riichi" && takesIntent(state, choose(offer)))
        .map(offerAction);
    const pass: PlayAction[] = takesIntent(state, PASS)
        ? [{ command: intentCommand(PASS), label: "Pass", pressed: null, tiles: [] }]
        : [];
    return [...riichi, ...offered, ...pass];
}

function intentsOf(plays: ReadonlyMap<number, TilePlay>): ReadonlyMap<number, LocalIntent> {
    return new Map(
        [...plays].flatMap(([tileId, play]): [number, LocalIntent][] =>
            play.intent === null ? [] : [[tileId, play.intent]],
        ),
    );
}

function viewerBoard(
    state: GameClientState,
    plays: ReadonlyMap<number, TilePlay>,
): BoardDisplayState | null {
    const { table, viewerSeat } = state;
    if (viewerSeat === null) {
        return null;
    }
    const board = tableStateToDisplayState(table, { bottomSeat: viewerSeat, reveal: "bottom" });
    if (board === null) {
        return null;
    }
    const [bottom, right, top, left] = board.players;
    return { ...board, players: [playHand(bottom, plays), right, top, left] };
}

/**
 * The round a table's result belongs to, which a reconnect's snapshot of it names alike: the server names an ended
 * round by its wind, dealer and honba, and no two rounds of a game share all three.
 */
function resultRound(table: TableState): string | null {
    if (table.roundEndResult === null) {
        return null;
    }
    return `${table.gameId}/${table.roundWind}/${table.dealerSeat}/${table.honbaSticks}`;
}

/** The result page the player turned to, while its round's result shows; else the first. */
function shownResultPage(table: TableState, ui: PlayUi): number {
    const round = resultRound(table);
    if (table.roundEndResult === null || ui.resultPage === null || ui.resultPage.round !== round) {
        return 0;
    }
    return roundEndPageAt(table.roundEndResult, ui.resultPage.page).index;
}

function pageAction(page: number): PlayAction {
    return { command: { kind: "show_result_page", page }, label: "Next", pressed: null, tiles: [] };
}

/** The confirm's button, when the dispatcher takes the confirm now. */
function confirmAction(state: GameClientState, confirm: RoundConfirm): PlayAction | null {
    if (
        (confirm.kind !== "owed" && confirm.kind !== "final") ||
        !takesIntent(state, CONFIRM_RESULT)
    ) {
        return null;
    }
    return {
        command: intentCommand(CONFIRM_RESULT),
        label: CONFIRM_LABELS[confirm.kind],
        pressed: null,
        tiles: [],
    };
}

/**
 * The round result's controls: while the confirm is owed (or the game's last result unread), Next through every page
 * but the last and the confirm on the last, so the player reads each winner of a double ron before confirming; once
 * the seat confirmed, that it waits for the others, with no button.
 */
function resultControls(state: GameClientState, page: number): ResultControls | null {
    const { roundConfirm, table } = state;
    if (roundConfirm === null || table.roundEndResult === null) {
        return null;
    }
    const countdown = roundConfirmCountdown(state);
    if (roundConfirm.kind === "sent" || roundConfirm.kind === "confirmed") {
        return { action: null, countdown, waiting: true };
    }
    const { count, index } = roundEndPageAt(table.roundEndResult, page);
    const action = index < count - 1 ? pageAction(index + 1) : confirmAction(state, roundConfirm);
    return { action, countdown, waiting: false };
}

/** The standings' button back to the game's last result, when the dispatcher takes it now. */
function lastResultAction(state: GameClientState): PlayAction | null {
    if (!takesIntent(state, SHOW_LAST_RESULT)) {
        return null;
    }
    return {
        command: intentCommand(SHOW_LAST_RESULT),
        label: "Last hand",
        pressed: null,
        tiles: [],
    };
}

const LEAVE: PlayCommand = { intent: { type: "leave" }, kind: "intent" };
const ASK_LEAVE: PlayCommand = { kind: "ask_leave" };

/** Whether leaving now hands a seat the session holds or works for to an AI. */
function leavingNeedsConfirm(session: SessionState | null): boolean {
    return session !== null && session.status !== "ended" && session.status !== "recovering";
}

/** The way back to the lobby, asking first while leaving would hand the seat to an AI. */
export function leaveControls(state: GameClientState, ui: PlayUi): LeaveControls {
    if (!leavingNeedsConfirm(state.session)) {
        return { command: LEAVE, confirming: false };
    }
    return { command: ASK_LEAVE, confirming: ui.confirmingLeave };
}

const DISCONNECTED_FAILURE: FailureDisplay = {
    detail: "The connection to the game ended.",
    reload: false,
    title: "Disconnected",
};

function closedFailure(code: number): FailureDisplay {
    if (code === CLOSE_CODE.REPLACED_BY_NEW_CONNECTION) {
        return {
            detail: "Your seat is now played from another tab or device.",
            reload: false,
            title: "Opened elsewhere",
        };
    }
    if (code === CLOSE_CODE.INVALID_GAME_ACTION) {
        return {
            detail: "The server ended your session after a move it could not accept.",
            reload: false,
            title: "Removed from the game",
        };
    }
    return DISCONNECTED_FAILURE;
}

/**
 * A refusal of the ticket: the handoff is forgotten already, so a reload asks the lobby for the player's game afresh
 * and lands wherever they play now.
 */
function refusedFailure(code: string): FailureDisplay {
    if (code === SESSION_ERROR_CODE.RECONNECT_ALREADY_ACTIVE) {
        return {
            detail: "The game server would not resume your seat on this connection.",
            reload: true,
            title: "Session error",
        };
    }
    if (code === SESSION_ERROR_CODE.INTERNAL_ERROR) {
        return {
            detail: "The game server could not go on with your session.",
            reload: true,
            title: "Server error",
        };
    }
    return {
        detail: "This game has ended, or this page no longer holds your seat in it.",
        reload: true,
        title: "Game unavailable",
    };
}

function exhaustedFailure(gameStarted: boolean): FailureDisplay {
    if (!gameStarted) {
        return {
            detail: "Could not connect to the game server.",
            reload: true,
            title: "Cannot reach the game",
        };
    }
    return {
        detail: "Could not reconnect to the game. An AI plays your seat meanwhile.",
        reload: true,
        title: "Connection lost",
    };
}

/** What an end that stays on the page tells the player; null for one that leaves it or shows the standings. */
function endFailure(reason: EndReason): FailureDisplay | null {
    switch (reason.kind) {
        case "closed": {
            return closedFailure(reason.code);
        }
        case "refused": {
            return refusedFailure(reason.code);
        }
        case "retries_exhausted": {
            return exhaustedFailure(reason.gameStarted);
        }
        case "recovery_failed": {
            return {
                detail: "The lobby did not say which game you play. Try again in a moment.",
                reload: true,
                title: "Can't reach the lobby",
            };
        }
        case "failed": {
            return {
                detail: "The game page ran into an error.",
                reload: true,
                title: "Something went wrong",
            };
        }
        case "game_ended":
        case "no_handoff":
        case "left":
        case "moved": {
            return null;
        }
        default: {
            return assertNever(reason);
        }
    }
}

/** What an end that stopped the session on the page tells the player; null while it runs or once it left. */
export function failureDisplay(session: SessionState | null): FailureDisplay | null {
    return session?.status === "ended" ? endFailure(session.reason) : null;
}

/**
 * The connection's notice while it is not holding the seat: finding the game; the seat this page held, lost to a
 * drop and being retried; or a connection that has failed since the page opened, being retried. The words stay the
 * same across the retries, so the live region reads them once. A page that only resumes its seat (a reload) shows
 * none.
 */
function connectionNotice(session: SessionState | null): PlayNotice | null {
    if (session === null || session.status === "ended" || session.status === "playing") {
        return null;
    }
    if (session.status === "recovering") {
        return { text: "Finding your game…", tone: "info" };
    }
    if (session.lostSeat) {
        return { text: "Connection lost. Reconnecting…", tone: "warning" };
    }
    if (session.attempts.transport > 0) {
        return { text: "Cannot reach the game. Retrying…", tone: "warning" };
    }
    return null;
}

function refusalText(code: string): string {
    if (code === SESSION_ERROR_CODE.RATE_LIMITED) {
        return "Too fast. Try that again";
    }
    if (code === GAME_ERROR_CODE.NOT_YOUR_TURN) {
        return "Not your turn";
    }
    return "That move was refused";
}

function timedNotice(notice: TimedNotice | null): PlayNotice | null {
    if (notice?.kind === "reconnected") {
        return { text: "Reconnected", tone: "success" };
    }
    if (notice?.kind === "refused") {
        return { text: refusalText(notice.code), tone: "warning" };
    }
    return null;
}

function unreadNotice(count: number): PlayNotice | null {
    if (count === 0) {
        return null;
    }
    const messages = count === 1 ? "A server message" : `${count} server messages`;
    return { text: `${messages} could not be read; the table may be wrong`, tone: "error" };
}

/**
 * The tile faces' notice once a load of the sprite failed, until one succeeds: the tiles show their names meanwhile,
 * and a reload is the player's way to try at once. The words stay the same across the retries.
 */
function tileSpriteNotice(status: TileSpriteStatus): PlayNotice | null {
    if (status !== "retrying" && status !== "failed") {
        return null;
    }
    return {
        action: { command: { kind: "reload" }, label: "Reload" },
        text: "Tile images did not load; tiles show their names",
        tone: "warning",
    };
}

/**
 * The final standings' notice once the game ended and every try at loading them failed: the board shows no panel
 * meanwhile, and a reload is the player's way to try at once.
 */
function standingsNotice(table: TableState, status: LoadStatus): PlayNotice | null {
    if (table.phase !== "game_ended" || status !== "failed") {
        return null;
    }
    return {
        action: { command: { kind: "reload" }, label: "Reload" },
        text: "The final standings did not load",
        tone: "error",
    };
}

function boardNotices(state: GameClientState, ui: PlayUi): PlayNotice[] {
    return [
        connectionNotice(state.session),
        timedNotice(state.notice),
        unreadNotice(state.unreadMessages),
        tileSpriteNotice(ui.tileSprite),
        standingsNotice(state.table, ui.standings),
    ].filter((notice) => notice !== null);
}

/** The live calls as the viewer's board shows them, keyed by when they were made. */
function liveCallouts(state: GameClientState): BoardCallouts | null {
    const { calls, viewerSeat } = state;
    if (calls === null || viewerSeat === null) {
        return null;
    }
    return { items: boardCallouts(calls.calls, viewerSeat), key: `call-${calls.at}` };
}

/**
 * The live board a client state shows its viewer, with the view's `ui` beside it: the table from the viewer's seat
 * with only its own hand face up, and the open decision as the hand's playable tiles and the buttons around them.
 * What may be played is the dispatcher's answer (`takesIntent`), never a rule restated here, so the board offers
 * exactly what stepping the intent would send.
 */
export function playDisplay(state: GameClientState, ui: PlayUi): PlayDisplay {
    const { furiten, table, viewerSeat } = state;
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    const picking = pickingRiichi(state, ui);
    const plays =
        viewer === undefined ? new Map<number, TilePlay>() : tilePlays(state, viewer, picking);
    const resultPage = shownResultPage(table, ui);
    const failure = failureDisplay(state.session);
    return {
        actions: decisionActions(state, picking),
        board: viewerBoard(state, plays),
        callouts: liveCallouts(state),
        countdown: decisionCountdown(state),
        failure,
        firstDealSeconds: firstDealCountdown(state),
        furiten: furiten && viewer !== undefined && table.phase === "in_round",
        lastResult: lastResultAction(state),
        leave: leaveControls(state, ui),
        notices: failure === null ? boardNotices(state, ui) : [],
        pinnedNameplate: ui.pinnedNameplate,
        result: resultControls(state, resultPage),
        resultOverStandings: state.roundConfirm?.kind === "final",
        resultPage,
        tileAction: picking ? RIICHI_ACTION : DISCARD_ACTION,
        tileIntents: intentsOf(plays),
        viewerSeat,
    };
}

/** The game's last result reopens on its first page; any other intent leaves the view's `ui` as it was. */
function uiAfterIntent(ui: PlayUi, intent: LocalIntent): PlayUi {
    return intent.type === "show_last_result" ? { ...ui, resultPage: null } : ui;
}

/**
 * The view's `ui` after a command: picking riichi's discard turns on or off for the open decision; the result's panel
 * turns to a page of the result showing, and the game's last result reopens on its first; a nameplate is pinned, or
 * none.
 */
export function nextPlayUi(state: GameClientState, ui: PlayUi, command: PlayCommand): PlayUi {
    switch (command.kind) {
        case "intent":
        case "reload": {
            return command.kind === "intent" ? uiAfterIntent(ui, command.intent) : ui;
        }
        case "ask_leave": {
            return { ...ui, confirmingLeave: true };
        }
        case "cancel_leave": {
            return { ...ui, confirmingLeave: false };
        }
        case "toggle_riichi_pick": {
            const waitId = state.decision?.waitId ?? null;
            return { ...ui, riichiPickWaitId: pickingRiichi(state, ui) ? null : waitId };
        }
        case "show_result_page": {
            const round = resultRound(state.table);
            return { ...ui, resultPage: round === null ? null : { page: command.page, round } };
        }
        case "pin_nameplate": {
            return { ...ui, pinnedNameplate: command.seat };
        }
        default: {
            return assertNever(command);
        }
    }
}
