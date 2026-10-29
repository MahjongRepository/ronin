import {
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type PlayerState,
    tableStateToDisplayState,
} from "@/entities/table";
import { type HandTile, type PlayableState, type TileFace, tile136toString } from "@/entities/tile";
import { assertNever } from "@/shared/lib";
import { CLIENT_MESSAGE_TYPE, GAME_ACTION } from "@/shared/protocol";

import { type DecisionCountdown, decisionCountdown } from "./countdown";
import { takesIntent } from "./dispatch";
import {
    type Decision,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type Offer,
} from "./types";

/** What a control of the board does: send the client an intent, or turn picking riichi's discard on or off. */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" };

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
 * this wait id, so a newer decision never inherits it.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
}

export const NO_PLAY_UI: PlayUi = { riichiPickWaitId: null };

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
    return {
        actions: decisionActions(state, picking),
        board: viewerBoard(state, plays),
        countdown: decisionCountdown(state),
        furiten: furiten && viewer !== undefined,
        tileAction: picking ? RIICHI_ACTION : DISCARD_ACTION,
        tileIntents: intentsOf(plays),
    };
}

/** The view's `ui` after a command: picking riichi's discard turns on or off for the open decision. */
export function nextPlayUi(state: GameClientState, ui: PlayUi, command: PlayCommand): PlayUi {
    if (command.kind === "intent") {
        return ui;
    }
    const waitId = state.decision?.waitId ?? null;
    return { riichiPickWaitId: pickingRiichi(state, ui) ? null : waitId };
}
