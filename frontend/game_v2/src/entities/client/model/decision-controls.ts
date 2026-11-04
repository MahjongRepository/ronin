import { type PlayerState, ponOfType } from "@/entities/table";
import {
    type MeldInput,
    type MeldTile,
    type PlayableState,
    type TileFace,
    meldTiles,
    tile136toString,
} from "@/entities/tile";
import { assertNever } from "@/shared/lib";
import { KAN_TYPE, tileType, tileTypeCopies } from "@/shared/protocol";

import { takesIntent } from "./intents";
import { decisionOf } from "./pending";
import {
    type EscapeStep,
    type PlayAction,
    type PlayCommand,
    type PlayUi,
    type TileChoiceKind,
    intentCommand,
} from "./play-ui";
import {
    type Decision,
    type DecisionIntent,
    type LiveClient,
    type LocalIntent,
    type Offer,
} from "./types";

const STEP_BACK: PlayCommand = { kind: "step_back" };

/**
 * How prominent a decision control is: a win (ron, tsumo, and kyuushu, which ends the hand too) above a call, kan or
 * riichi, and a pass or the way back below them.
 */
export type ActionRank = "win" | "call" | "pass";

/**
 * A control of the open decision: a first step's one control per kind of offer, a second step's choice of tiles drawn
 * as its meld will lie (`group`), the riichi toggle, a pass or the way back.
 */
export interface DecisionAction extends PlayAction {
    readonly rank: ActionRank;
    /** A choice of tiles at a call's second step, laid as the meld will lie; null for any other control. */
    readonly group: readonly MeldTile[] | null;
}

/** Where an answerable decision stands: open or past its deadline. */
export type DecisionStanding = "open" | "expired";

/** How each tile of the viewer's hand plays now: its mark, and what tapping it sends when selectable. */
export interface TilePlay {
    readonly state: PlayableState;
    readonly intent: DecisionIntent | null;
}

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
const BACK = "Back";

function choose(offer: Offer): DecisionIntent {
    return { offer, type: "choose" };
}

/** The tile a submitted discard or riichi played, which the hand marks while the server answers. */
function submittedTileId(decision: Decision | null): number | null {
    if (decision?.status.kind !== "submitted") {
        return null;
    }
    const { intent } = decision.status;
    if (intent.type === "discard") {
        return intent.tileId;
    }
    return intent.type === "choose" && intent.offer.kind === "riichi" ? intent.offer.tileId : null;
}

type IntentJudge = (intent: DecisionIntent) => boolean;

function judgeNow(state: LiveClient): IntentJudge {
    return (intent) => takesIntent(state, intent);
}

/** The offers the judge takes, in the order the server listed them. */
function takenOffers(state: LiveClient, takes: IntentJudge): Offer[] {
    const offers = decisionOf(state)?.offers ?? [];
    return offers.filter((offer) => takes(choose(offer)));
}

function pickingRiichiBy(state: LiveClient, ui: PlayUi, takes: IntentJudge): boolean {
    const decision = decisionOf(state);
    return (
        decision !== null &&
        decision.waitId === ui.riichiPickWaitId &&
        takenOffers(state, takes).some((offer) => offer.kind === "riichi")
    );
}

/** Whether the player is picking riichi's discard: toggled for this decision, which still takes a riichi. */
export function pickingRiichi(state: LiveClient, ui: PlayUi): boolean {
    return pickingRiichiBy(state, ui, judgeNow(state));
}

function isTileChoiceKind(kind: Offer["kind"]): kind is TileChoiceKind {
    return kind === "chi" || kind === "kan";
}

function choosingTilesBy(state: LiveClient, ui: PlayUi, takes: IntentJudge): TileChoiceKind | null {
    const decision = decisionOf(state);
    const choice = ui.tileChoice;
    if (decision === null || choice === null || decision.waitId !== choice.waitId) {
        return null;
    }
    const choices = takenOffers(state, takes).filter((offer) => offer.kind === choice.kind);
    return choices.length > 1 ? choice.kind : null;
}

/** The kind of call whose tiles the player is choosing: toggled for this decision, which still takes two of it. */
export function choosingTiles(state: LiveClient, ui: PlayUi): TileChoiceKind | null {
    return choosingTilesBy(state, ui, judgeNow(state));
}

/** The intent a tap on `tileId` asks for: riichi with it while riichi's discard is picked, else its discard. */
function tileIntent(tileId: number, picking: boolean): DecisionIntent {
    return picking ? choose({ kind: "riichi", tileId }) : { tileId, type: "discard" };
}

/**
 * How each of the viewer's tiles plays, by asking the dispatcher whether it takes the tile's intent: selectable
 * when it does (declaring, while riichi's discard is picked); before riichi, disabled when an open turn holds it back
 * (kuikae or not riichi's while picking it); the tile an answer played, selected; otherwise waiting. Every
 * tile stays a button, so focus stays in the hand.
 */
export function tilePlays(
    state: LiveClient,
    viewer: PlayerState,
    picking: boolean,
): Map<number, TilePlay> {
    const decision = decisionOf(state);
    const played = submittedTileId(decision);
    const openTurn = decision?.kind === "turn" && decision.status.kind !== "submitted";
    return new Map(
        viewer.tiles.map((tileId): [number, TilePlay] => {
            const intent = tileIntent(tileId, picking);
            if (takesIntent(state, intent)) {
                return [tileId, { intent, state: picking ? "declaring" : "selectable" }];
            }
            const waiting: PlayableState = openTurn && !viewer.isRiichi ? "disabled" : "waiting";
            return [tileId, { intent: null, state: tileId === played ? "selected" : waiting }];
        }),
    );
}

export function intentsOf(plays: ReadonlyMap<number, TilePlay>): ReadonlyMap<number, LocalIntent> {
    return new Map(
        [...plays].flatMap(([tileId, play]): [number, LocalIntent][] =>
            play.intent === null ? [] : [[tileId, play.intent]],
        ),
    );
}

/** The tiles that tell an offer from another of its kind: a chi's pair, the tile a pon or kan takes. */
function offerTiles(offer: Offer): TileFace[] {
    switch (offer.kind) {
        case "chi": {
            return offer.sequence.map((tile) => tile136toString(tile));
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

const WIN_KINDS: ReadonlySet<Offer["kind"]> = new Set(["ron", "tsumo", "kyuushu"]);

type ControlFields = Pick<DecisionAction, "label" | "command" | "rank"> &
    Partial<Pick<DecisionAction, "group" | "pressed" | "tiles">>;

function control(fields: ControlFields): DecisionAction {
    return { group: null, pressed: null, tiles: [], ...fields };
}

function offerAction(offer: Offer): DecisionAction {
    return control({
        command: intentCommand(choose(offer)),
        label: OFFER_LABELS[offer.kind],
        rank: WIN_KINDS.has(offer.kind) ? "win" : "call",
        tiles: offerTiles(offer),
    });
}

/**
 * An added kan laid as it will lie: the pon it adds to, with the added tile stacked on its called one. Opening the
 * decision checked the pon is there (Desync), so a missing one is a bug.
 */
function addedKanGroup(state: LiveClient, tileId: number): MeldTile[] {
    const { table, viewerSeat } = state;
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    const pon = ponOfType(viewer?.melds ?? [], tileType(tileId));
    if (pon === undefined) {
        throw new Error(
            `an added kan of tile ${tileId} needs a pon of its type, which opening it checked`,
        );
    }
    const tileIds = [...pon.tileIds, tileId];
    return meldTiles({ ...pon, addedTileId: tileId, meldType: "added_kan", tileIds });
}

/**
 * A chi's or kan's tiles laid as its meld will lie: a chi's called tile turned toward its feeder, a closed kan's ends
 * face down, an added kan's added tile stacked on its pon's called one, an open kan's called tile turned.
 */
function offerGroup(
    state: LiveClient,
    offer: Extract<Offer, { kind: TileChoiceKind }>,
): MeldTile[] {
    const { viewerSeat } = state;
    const decision = decisionOf(state);
    if (viewerSeat === null) {
        throw new Error("a choice of tiles needs the viewer's seat, which every decision has");
    }
    const seats = {
        callerSeat: viewerSeat,
        fromSeat: decision?.kind === "call" ? decision.fromSeat : null,
    };
    if (offer.kind === "chi") {
        const tileIds = [offer.tileId, ...offer.sequence];
        return meldTiles({ ...seats, calledTileId: offer.tileId, meldType: "chi", tileIds });
    }
    return kanGroup(state, offer, seats);
}

/** A kan laid as it will lie: an open one's called tile turned, an added one stacked, a closed one's ends face down. */
function kanGroup(
    state: LiveClient,
    offer: Extract<Offer, { kind: "kan" }>,
    seats: Pick<MeldInput, "callerSeat" | "fromSeat">,
): MeldTile[] {
    const tileIds = tileTypeCopies(tileType(offer.tileId));
    if (offer.kanType === KAN_TYPE.OPEN) {
        return meldTiles({ ...seats, calledTileId: offer.tileId, meldType: "open_kan", tileIds });
    }
    if (offer.kanType === KAN_TYPE.ADDED) {
        return addedKanGroup(state, offer.tileId);
    }
    const closed = { calledTileId: null, callerSeat: seats.callerSeat, fromSeat: null } as const;
    return meldTiles({ ...closed, meldType: "closed_kan", tileIds });
}

/**
 * A call's second step: one choice per tile group the dispatcher takes, drawn as the meld will lie; then the call's own
 * control, pressed, which steps back when pressed again and so stays where the first step had it, last before the
 * band; and Back in the place of Pass.
 */
function tileChoiceActions(
    state: LiveClient,
    kind: TileChoiceKind,
    offers: readonly Offer[],
): DecisionAction[] {
    const label = OFFER_LABELS[kind];
    const choices = offers.flatMap((offer): DecisionAction[] => {
        if (offer.kind !== kind || (offer.kind !== "chi" && offer.kind !== "kan")) {
            return [];
        }
        const command = intentCommand(choose(offer));
        const group = offerGroup(state, offer);
        return [control({ command, group, label, rank: "call", tiles: offerTiles(offer) })];
    });
    const toggle: PlayCommand = { kind: "toggle_tile_choice", offer: kind };
    return [
        ...choices,
        control({ command: toggle, label, pressed: true, rank: "call" }),
        control({ command: STEP_BACK, label: BACK, rank: "pass" }),
    ];
}

/**
 * A decision's first step: the wins first, then riichi as one toggle that picks its discard from the hand, then one
 * control per other kind of offer in the order the server listed them (a kind with a choice of tiles opens its second
 * step), then a pass.
 */
function firstStepActions(
    offers: readonly Offer[],
    picking: boolean,
    takes: IntentJudge,
): DecisionAction[] {
    const wins = offers.filter((offer) => WIN_KINDS.has(offer.kind)).map(offerAction);
    const riichiToggle = control({
        command: { kind: "toggle_riichi_pick" },
        label: OFFER_LABELS.riichi,
        pressed: picking,
        rank: "call",
    });
    const riichi = offers.some((offer) => offer.kind === "riichi") ? [riichiToggle] : [];
    const calls = offers.filter((offer) => !WIN_KINDS.has(offer.kind) && offer.kind !== "riichi");
    const kinds = [...new Set(calls.map((offer) => offer.kind))];
    const perKind = kinds.flatMap((kind): DecisionAction[] => {
        const ofKind = calls.filter((offer) => offer.kind === kind);
        if (ofKind.length === 1 || !isTileChoiceKind(kind)) {
            return ofKind.map(offerAction);
        }
        const command: PlayCommand = { kind: "toggle_tile_choice", offer: kind };
        return [control({ command, label: OFFER_LABELS[kind], pressed: false, rank: "call" })];
    });
    const passControl = control({ command: intentCommand(PASS), label: "Pass", rank: "pass" });
    const pass = takes(PASS) ? [passControl] : [];
    return [...wins, ...riichi, ...perKind, ...pass];
}

export function decisionActions(state: LiveClient, ui: PlayUi): DecisionAction[] {
    if (decisionStanding(state) === null) {
        return [];
    }
    const takes = judgeNow(state);
    const offers = takenOffers(state, takes);
    const choosing = choosingTilesBy(state, ui, takes);
    return choosing === null
        ? firstStepActions(offers, pickingRiichiBy(state, ui, takes), takes)
        : tileChoiceActions(state, choosing, offers);
}

/**
 * What Escape steps back from, with the toggle that opened it: a call's choice of tiles, else the riichi toggle;
 * neither once answered.
 */
export function escapeStep(state: LiveClient, ui: PlayUi): EscapeStep | null {
    if (decisionOf(state)?.status.kind === "submitted") {
        return null;
    }
    const choosing = choosingTiles(state, ui);
    if (choosing !== null) {
        return { command: STEP_BACK, opener: { kind: "toggle_tile_choice", offer: choosing } };
    }
    return pickingRiichi(state, ui)
        ? { command: STEP_BACK, opener: { kind: "toggle_riichi_pick" } }
        : null;
}

export function decisionStanding(state: LiveClient): DecisionStanding | null {
    const status = decisionOf(state)?.status.kind;
    return status === undefined || status === "submitted" ? null : status;
}
