import {
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type PlayerState,
    type TableState,
    roundEndPageAt,
    tableStateToDisplayState,
} from "@/entities/table";
import { type HandTile, type PlayableState, type TileFace, tile136toString } from "@/entities/tile";
import { assertNever } from "@/shared/lib";
import { CLIENT_MESSAGE_TYPE, GAME_ACTION } from "@/shared/protocol";

import { type DecisionCountdown, decisionCountdown, roundConfirmCountdown } from "./countdown";
import { takesIntent } from "./dispatch";
import {
    type Decision,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type Offer,
    type PlayIntent,
    type RoundConfirm,
} from "./types";

/**
 * What a control of the board does: send the client an intent, turn picking riichi's discard on or off, or turn the
 * round result's panel to a page.
 */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" }
    | { readonly kind: "show_result_page"; readonly page: number };

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
 * this wait id, so a newer decision never inherits it; and the page of a round's result the player turned to, for
 * the round it names, so a newer result opens on its first page while a reconnect's copy of the same one keeps it.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
    readonly resultPage: { readonly round: string; readonly page: number } | null;
}

export const NO_PLAY_UI: PlayUi = { resultPage: null, riichiPickWaitId: null };

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
    readonly tileAction: string;
    readonly tileIntents: ReadonlyMap<number, LocalIntent>;
    readonly actions: readonly PlayAction[];
    readonly countdown: DecisionCountdown | null;
    readonly furiten: boolean;
    /** The page of the round's result the panel shows, clamped to its pages; 0 with no result. */
    readonly resultPage: number;
    /** The result panel's controls while the viewer has a round result to confirm or waits on one; else null. */
    readonly result: ResultControls | null;
    /** Whether the game's last result still shows over the standings, until the player dismisses it. */
    readonly resultOverStandings: boolean;
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
    return {
        actions: decisionActions(state, picking),
        board: viewerBoard(state, plays),
        countdown: decisionCountdown(state),
        furiten: furiten && viewer !== undefined,
        result: resultControls(state, resultPage),
        resultOverStandings: state.roundConfirm?.kind === "final",
        resultPage,
        tileAction: picking ? RIICHI_ACTION : DISCARD_ACTION,
        tileIntents: intentsOf(plays),
    };
}

/**
 * The view's `ui` after a command: picking riichi's discard turns on or off for the open decision; the result's panel
 * turns to a page of the result showing.
 */
export function nextPlayUi(state: GameClientState, ui: PlayUi, command: PlayCommand): PlayUi {
    switch (command.kind) {
        case "intent": {
            return ui;
        }
        case "toggle_riichi_pick": {
            const waitId = state.decision?.waitId ?? null;
            return { ...ui, riichiPickWaitId: pickingRiichi(state, ui) ? null : waitId };
        }
        case "show_result_page": {
            const round = resultRound(state.table);
            return { ...ui, resultPage: round === null ? null : { page: command.page, round } };
        }
        default: {
            return assertNever(command);
        }
    }
}
