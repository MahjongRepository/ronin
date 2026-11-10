import { type PlayerState } from "@/entities/table";
import { type PlayableState, type TileFace, tile136toString } from "@/entities/tile";
import { type MessageKey, t } from "@/shared/i18n";
import { assertNever } from "@/shared/lib";
import { tileType } from "@/shared/protocol";

import { takesIntent } from "./intents";
import { decisionOf } from "./pending";
import {
    type EscapeStep,
    type PlayAction,
    type PlayUi,
    RIICHI_PICK_STEP_BACK,
    intentCommand,
} from "./play-ui";
import {
    type Decision,
    type DecisionIntent,
    type LiveClient,
    type LocalIntent,
    type Offer,
} from "./types";

/**
 * Where a decision control ranks: a win (ron, tsumo, and kyuushu, which ends the hand too) above a call, kan or
 * riichi, and a pass below them.
 */
export type ActionRank = "win" | "call" | "pass";

/** What a control answers with, which colours it: an offer's kind, or the pass. */
export type ActionKind = Offer["kind"] | "pass";

/** A control of the open decision: one per offer, riichi as one toggle, and a pass. */
export interface DecisionAction extends PlayAction {
    readonly rank: ActionRank;
    readonly kind: ActionKind;
    /** The digit key that presses it (`numberedActions`); null for one Escape answers or none reaches. */
    readonly digit: number | null;
}

/** The highest digit key a control takes; a tenth control has none. */
const MAX_ACTION_DIGIT = 9;

/** Where an answerable decision stands: open or past its deadline. */
export type DecisionStanding = "open" | "expired";

/** How each tile of the viewer's hand plays now: its mark, and what tapping it sends when selectable. */
export interface TilePlay {
    readonly state: PlayableState;
    readonly intent: DecisionIntent | null;
}

const OFFER_LABELS: Readonly<Record<Offer["kind"], MessageKey>> = {
    chi: "game.call.chi",
    kan: "game.call.kan",
    kyuushu: "game.call.abort",
    pon: "game.call.pon",
    riichi: "game.call.riichi",
    ron: "game.call.ron",
    tsumo: "game.call.tsumo",
};

const PASS: DecisionIntent = { type: "pass" };

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

/** The intent a tap on `tileId` asks for: riichi with it while riichi's discard is picked, else its discard. */
function tileIntent(tileId: number, picking: boolean): DecisionIntent {
    return picking ? choose({ kind: "riichi", tileId }) : { tileId, type: "discard" };
}

/** The tile a first finger tap armed for the open decision; null when it was armed for an earlier one. */
export function armedTileId(state: LiveClient, ui: PlayUi): number | null {
    const waitId = decisionOf(state)?.waitId;
    return ui.armedTile !== null && ui.armedTile.waitId === waitId ? ui.armedTile.tileId : null;
}

function takenTileState(tileId: number, picking: boolean, armed: number | null): PlayableState {
    if (picking) {
        return "declaring";
    }
    return tileId === armed ? "armed" : "selectable";
}

/**
 * How each of the viewer's tiles plays, by asking the dispatcher whether it takes the tile's intent: selectable
 * when it does (armed, once a finger tapped it; declaring, while riichi's discard is picked); before riichi, disabled when an open turn holds it back
 * (kuikae or not riichi's while picking it); the tile an answer played, selected; otherwise waiting. Every
 * tile stays a button, so focus stays in the hand.
 */
export function tilePlays(
    state: LiveClient,
    viewer: PlayerState,
    { armed, picking }: { readonly armed: number | null; readonly picking: boolean },
): Map<number, TilePlay> {
    const decision = decisionOf(state);
    const played = submittedTileId(decision);
    const openTurn = decision?.kind === "turn" && decision.status.kind !== "submitted";
    return new Map(
        viewer.tiles.map((tileId): [number, TilePlay] => {
            const intent = tileIntent(tileId, picking);
            if (takesIntent(state, intent)) {
                return [tileId, { intent, state: takenTileState(tileId, picking, armed) }];
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

/** A red five's face, which a chi lists after the plain five's. */
function isRedFace(face: TileFace): boolean {
    return face.startsWith("0");
}

/** Where a chi stands among the chis of one call: by its hand tiles low to high, as the hand lies, a red five last. */
function chiRank(offer: Extract<Offer, { kind: "chi" }>): readonly number[] {
    const types = offer.sequence.map((tile) => tileType(tile)).toSorted((low, high) => low - high);
    const reds = offer.sequence.filter((tile) => isRedFace(tile136toString(tile))).length;
    return [...types, reds];
}

function byChiRank(first: Offer, second: Offer): number {
    if (first.kind !== "chi" || second.kind !== "chi") {
        return 0;
    }
    const ranks = chiRank(first).map((rank, index) => rank - (chiRank(second)[index] ?? 0));
    return ranks.find((difference) => difference !== 0) ?? 0;
}

/**
 * The hand's tiles a control shows, only where they tell something the table does not: a chi's pair, low to high, and
 * the tile of a kan offered beside another kan. A pon or a lone kan names its tile on the table already.
 */
function offerTiles(offer: Offer, ofKind: number): TileFace[] {
    switch (offer.kind) {
        case "chi": {
            return offer.sequence
                .toSorted((low, high) => tileType(low) - tileType(high))
                .map((tile) => tile136toString(tile));
        }
        case "kan": {
            return ofKind > 1 ? [tile136toString(offer.tileId)] : [];
        }
        case "pon":
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

type ControlFields = Pick<DecisionAction, "label" | "command" | "rank" | "kind"> &
    Partial<Pick<DecisionAction, "pressed" | "tiles">>;

function control(fields: ControlFields): DecisionAction {
    return { digit: null, pressed: null, tiles: [], ...fields };
}

function offerAction(offer: Offer, ofKind: number): DecisionAction {
    return control({
        command: intentCommand(choose(offer)),
        kind: offer.kind,
        label: t(OFFER_LABELS[offer.kind]),
        rank: WIN_KINDS.has(offer.kind) ? "win" : "call",
        tiles: offerTiles(offer, ofKind),
    });
}

/**
 * The decision's controls: the wins first, then riichi as one toggle that picks its discard from the hand, then one
 * control per other offer, kinds in the order the server listed them and a kind's chis as the hand lies, then a pass.
 */
function offerActions(
    offers: readonly Offer[],
    picking: boolean,
    takes: IntentJudge,
): DecisionAction[] {
    const wins = offers
        .filter((offer) => WIN_KINDS.has(offer.kind))
        .map((offer) => offerAction(offer, 1));
    const riichiToggle = control({
        command: { kind: "toggle_riichi_pick" },
        kind: "riichi",
        label: t(OFFER_LABELS.riichi),
        pressed: picking,
        rank: "call",
    });
    const riichi = offers.some((offer) => offer.kind === "riichi") ? [riichiToggle] : [];
    const calls = offers.filter((offer) => !WIN_KINDS.has(offer.kind) && offer.kind !== "riichi");
    const kinds = [...new Set(calls.map((offer) => offer.kind))];
    const perKind = kinds.flatMap((kind): DecisionAction[] => {
        const ofKind = calls.filter((offer) => offer.kind === kind).toSorted(byChiRank);
        return ofKind.map((offer) => offerAction(offer, ofKind.length));
    });
    const passControl = control({
        command: intentCommand(PASS),
        kind: "pass",
        label: t("game.button.pass"),
        rank: "pass",
    });
    const pass = takes(PASS) ? [passControl] : [];
    return [...wins, ...riichi, ...perKind, ...pass];
}

/** The controls with their digit keys, 1 up, in the order the mapper lists them: every control but the pass. */
function numberedActions(actions: readonly DecisionAction[]): DecisionAction[] {
    const numbered = actions.filter((action) => action.rank !== "pass");
    return actions.map((action) => {
        const digit = numbered.indexOf(action) + 1;
        return digit === 0 || digit > MAX_ACTION_DIGIT ? action : { ...action, digit };
    });
}

export function decisionActions(state: LiveClient, ui: PlayUi): DecisionAction[] {
    if (decisionStanding(state) === null) {
        return [];
    }
    const takes = judgeNow(state);
    const offers = takenOffers(state, takes);
    return numberedActions(offerActions(offers, pickingRiichiBy(state, ui, takes), takes));
}

/** What Escape steps back from: riichi's pick of a discard; nothing once answered. */
export function escapeStep(state: LiveClient, ui: PlayUi): EscapeStep | null {
    if (decisionOf(state)?.status.kind === "submitted") {
        return null;
    }
    return pickingRiichi(state, ui) ? RIICHI_PICK_STEP_BACK : null;
}

export function decisionStanding(state: LiveClient): DecisionStanding | null {
    const status = decisionOf(state)?.status.kind;
    return status === undefined || status === "submitted" ? null : status;
}
