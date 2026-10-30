import { type EndReason, type SessionState, hasLostSeat } from "@/entities/session";
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
    type MeldInput,
    type MeldTile,
    type PlayableState,
    type TileFace,
    type TileSpriteStatus,
    meldTiles,
    tile136toString,
} from "@/entities/tile";
import { type LoadStatus, assertNever } from "@/shared/lib";
import {
    CALL_TYPE,
    CLOSE_CODE,
    GAME_ERROR_CODE,
    KAN_TYPE,
    SESSION_ERROR_CODE,
} from "@/shared/protocol";

import {
    type DecisionCountdown,
    decisionCountdown,
    firstDealCountdown,
    roundConfirmCountdown,
} from "./countdown";
import { sameIntent } from "./decision";
import { takesIntent } from "./dispatch";
import { PLAY_SWITCHES } from "./play-switches";
import {
    type Decision,
    type DecisionIntent,
    type GameClientState,
    type LocalIntent,
    type Offer,
    type PlayIntent,
    type PlaySwitch,
    type RoundConfirm,
    type TimedNotice,
} from "./types";

/** A call whose offers of one kind differ by their tiles (which chi, which kan), taken in two steps. */
export type TileChoiceKind = "chi" | "kan";

/**
 * What a control of the page does: send the client an intent, turn picking riichi's discard on or off, open or close
 * a call's choice of tiles, step back from either (Back, Escape), turn the round result's panel to a page, pin a
 * nameplate (or none) for the others' score differences, ask to leave mid-game or take that back, or reload the page
 * after a failure.
 */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" }
    | { readonly kind: "toggle_tile_choice"; readonly offer: TileChoiceKind }
    | { readonly kind: "step_back" }
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
    /** Once the decision is answered, whether this control sent the answer; false while it is open. */
    readonly chosen: boolean;
}

/**
 * A play switch on the board: its label, whether it is on, and the command turning it, which sends nothing itself.
 */
export interface SwitchControl {
    readonly playSwitch: PlaySwitch;
    readonly label: string;
    readonly on: boolean;
    readonly command: PlayCommand;
}

/** Where the open decision stands for its controls: open, past its deadline (still answerable), or answered. */
export type DecisionStanding = "open" | "expired" | "submitted";

/**
 * What the view holds beside the client state: that the player is picking riichi's discard, or choosing a call's
 * tiles, for the decision of this wait id, so a newer decision never inherits either; the page of a round's result the player turned to, for
 * the round it names, so a newer result opens on its first page while a reconnect's copy of the same one keeps it;
 * the nameplate pinned for the others' score differences, which stays pinned until the player unpins it, since the
 * viewer's seat stays at the bottom; that the player asked to leave mid-game and has yet to confirm it; and where the
 * tile sprite's load and the final standings' stand, which the page's IO owns.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
    readonly tileChoice: { readonly waitId: number; readonly kind: TileChoiceKind } | null;
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
    tileChoice: null,
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
    /** The open decision's controls, ranked; an answered one keeps them, showing which sent the answer. */
    readonly actions: readonly DecisionAction[];
    /** Where the viewer's decision stands; null with none. */
    readonly decisionStanding: DecisionStanding | null;
    /** What Escape does: step back from a call's choice of tiles or the riichi toggle; null with neither on. */
    readonly escape: PlayCommand | null;
    readonly countdown: DecisionCountdown | null;
    /** The seat is furiten, shown only while a round plays, never under its result or the standings. */
    readonly furiten: boolean;
    /** The play switches, while the player may turn them (a live seat in a round); else none. */
    readonly switches: readonly SwitchControl[];
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

const SWITCH_LABELS: Readonly<Record<PlaySwitch, string>> = {
    auto_discard: "Auto discard",
    auto_win: "Auto win",
    no_calls: "No calls",
};

const PASS: DecisionIntent = { type: "pass" };
const BACK = "Back";
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
    const { intent } = decision.status;
    if (intent.type === "discard") {
        return intent.tileId;
    }
    return intent.type === "choose" && intent.offer.kind === "riichi" ? intent.offer.tileId : null;
}

/**
 * The state as the decision stood for its answer: an answered decision reopened, so its controls are drawn as they
 * were when the player answered, and never move under the answer.
 */
function asAnswered(state: GameClientState): GameClientState {
    const { decision } = state;
    if (decision?.status.kind !== "submitted") {
        return state;
    }
    return { ...state, decision: { ...decision, status: { kind: "open" } } };
}

/** The offers the client would answer now, in the order the server listed them. */
function takenOffers(state: GameClientState): Offer[] {
    const offers = state.decision?.offers ?? [];
    return offers.filter((offer) => takesIntent(state, choose(offer)));
}

/** The riichi offers the client would answer now: what the riichi toggle picks from. */
function takenRiichiOffers(state: GameClientState): Offer[] {
    return takenOffers(state).filter((offer) => offer.kind === "riichi");
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

function isTileChoiceKind(kind: Offer["kind"]): kind is TileChoiceKind {
    return kind === "chi" || kind === "kan";
}

/** The kind of call whose tiles the player is choosing: toggled for this decision, which still takes two of it. */
function choosingTiles(state: GameClientState, ui: PlayUi): TileChoiceKind | null {
    const { decision } = state;
    const choice = ui.tileChoice;
    if (decision === null || choice === null || decision.waitId !== choice.waitId) {
        return null;
    }
    const choices = takenOffers(state).filter((offer) => offer.kind === choice.kind);
    return choices.length > 1 ? choice.kind : null;
}

/** The intent a tap on `tileId` asks for: riichi with it while riichi's discard is picked, else its discard. */
function tileIntent(tileId: number, picking: boolean): DecisionIntent {
    return picking ? choose({ kind: "riichi", tileId }) : { tileId, type: "discard" };
}

/**
 * How each of the viewer's tiles plays, by asking the dispatcher whether it takes the tile's intent: selectable
 * when it does (declaring, while riichi's discard is picked); on an open turn, disabled when it does not (kuikae,
 * riichi, or not riichi's while picking it); the tile an answer played, selected; any other moment, waiting. Every
 * tile stays a button, so focus stays in the hand.
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
                return [tileId, { intent, state: picking ? "declaring" : "selectable" }];
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

const WIN_KINDS: ReadonlySet<Offer["kind"]> = new Set(["ron", "tsumo", "kyuushu"]);
const COPIES = [0, 1, 2, 3] as const;

type ControlFields = Pick<DecisionAction, "label" | "command" | "rank"> &
    Partial<Pick<DecisionAction, "group" | "pressed" | "tiles">>;

function control(fields: ControlFields): DecisionAction {
    return { chosen: false, group: null, pressed: null, tiles: [], ...fields };
}

function offerAction(offer: Offer): DecisionAction {
    return control({
        command: intentCommand(choose(offer)),
        label: OFFER_LABELS[offer.kind],
        rank: WIN_KINDS.has(offer.kind) ? "win" : "call",
        tiles: offerTiles(offer),
    });
}

/** Every copy of a tile's type: a kan's four tiles. */
function typeCopies(tileId: number): number[] {
    const type = Math.floor(tileId / 4);
    return COPIES.map((copy) => type * 4 + copy);
}

/** An added kan laid as it will lie: the pon it adds to, with the added tile stacked on its called one. */
function addedKanGroup(state: GameClientState, tileId: number): MeldTile[] | null {
    const { table, viewerSeat } = state;
    const copies = typeCopies(tileId);
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    const pon = viewer?.melds.find(
        (meld) => meld.meldType === "pon" && meld.tileIds.some((id) => copies.includes(id)),
    );
    if (pon === undefined) {
        return null;
    }
    const tileIds = [...pon.tileIds, tileId];
    return meldTiles({ ...pon, addedTileId: tileId, meldType: "added_kan", tileIds });
}

/**
 * A chi's or kan's tiles laid as its meld will lie: a chi's called tile turned toward its feeder, a closed kan's ends
 * face down, an added kan's added tile stacked on its pon's called one, an open kan's called tile turned.
 */
function offerGroup(
    state: GameClientState,
    offer: Extract<Offer, { kind: TileChoiceKind }>,
): MeldTile[] {
    const { decision, viewerSeat } = state;
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
    state: GameClientState,
    offer: Extract<Offer, { kind: "kan" }>,
    seats: Pick<MeldInput, "callerSeat" | "fromSeat">,
): MeldTile[] {
    const tileIds = typeCopies(offer.tileId);
    if (offer.kanType === KAN_TYPE.OPEN) {
        return meldTiles({ ...seats, calledTileId: offer.tileId, meldType: "open_kan", tileIds });
    }
    const added = offer.kanType === KAN_TYPE.ADDED ? addedKanGroup(state, offer.tileId) : null;
    const closed = { calledTileId: null, callerSeat: seats.callerSeat, fromSeat: null } as const;
    return added ?? meldTiles({ ...closed, meldType: "closed_kan", tileIds });
}

/**
 * A call's second step: one choice per tile group the dispatcher takes, drawn as the meld will lie; then the call's own
 * control, pressed, which steps back when pressed again and so stays where the first step had it, last before the
 * band; and Back in the place of Pass.
 */
function tileChoiceActions(
    state: GameClientState,
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
        control({ command: { kind: "step_back" }, label: BACK, rank: "pass" }),
    ];
}

/**
 * A decision's first step: the wins first, then riichi as one toggle that picks its discard from the hand, then one
 * control per other kind of offer in the order the server listed them (a kind with a choice of tiles opens its second
 * step), then a pass.
 */
function firstStepActions(
    state: GameClientState,
    offers: readonly Offer[],
    picking: boolean,
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
    const pass = takesIntent(state, PASS) ? [passControl] : [];
    return [...wins, ...riichi, ...perKind, ...pass];
}

/** Whether pressing `candidate` gives the answer the decision was answered with. */
function sentBy(candidate: DecisionAction, sent: DecisionIntent): boolean {
    if (candidate.command.kind !== "intent") {
        return false;
    }
    const { intent } = candidate.command;
    if (intent.type !== "choose" && intent.type !== "pass" && intent.type !== "discard") {
        return false;
    }
    return sameIntent(intent, sent);
}

/**
 * The decision's controls, each one the dispatcher would answer now: the first step, or the second while the player
 * chooses a call's tiles. An answered decision keeps the controls it was answered from, marking the one that sent the
 * answer, so nothing moves while the server answers.
 */
function decisionActions(state: GameClientState, ui: PlayUi): DecisionAction[] {
    if (passedByNoCalls(state)) {
        return [];
    }
    const answered = asAnswered(state);
    const offers = takenOffers(answered);
    const choosing = choosingTiles(answered, ui);
    const controls =
        choosing === null
            ? firstStepActions(answered, offers, pickingRiichi(answered, ui))
            : tileChoiceActions(answered, choosing, offers);
    const status = state.decision?.status;
    if (status?.kind !== "submitted") {
        return controls;
    }
    return controls.map((candidate) => answeredBy(candidate, sentBy(candidate, status.intent)));
}

function answeredBy(candidate: DecisionAction, chosen: boolean): DecisionAction {
    return { ...candidate, chosen };
}

/** What Escape steps back from: a call's choice of tiles, else the riichi toggle; neither once answered. */
function escapeCommand(state: GameClientState, ui: PlayUi): PlayCommand | null {
    if (state.decision?.status.kind === "submitted") {
        return null;
    }
    const stepping = choosingTiles(state, ui) !== null || pickingRiichi(state, ui);
    return stepping ? { kind: "step_back" } : null;
}

function intentsOf(plays: ReadonlyMap<number, TilePlay>): ReadonlyMap<number, LocalIntent> {
    return new Map(
        [...plays].flatMap(([tileId, play]): [number, LocalIntent][] =>
            play.intent === null ? [] : [[tileId, play.intent]],
        ),
    );
}

/**
 * A chankan offer's source, the kan it may rob, as the declarer's board position and the meld's index (oldest first);
 * null for any other decision, so the mark goes once the offer resolves.
 */
function kanSource(state: GameClientState): { position: number; meld: number } | null {
    const { decision, table, viewerSeat } = state;
    if (
        decision?.kind !== "call" ||
        decision.callType !== CALL_TYPE.CHANKAN ||
        viewerSeat === null
    ) {
        return null;
    }
    const declarer = table.players.find((player) => player.seat === decision.fromSeat);
    const meld =
        declarer?.melds.findIndex(
            (candidate) =>
                candidate.tileIds.includes(decision.tileId) ||
                candidate.addedTileId === decision.tileId,
        ) ?? -1;
    return meld === -1 ? null : { meld, position: (decision.fromSeat - viewerSeat + 4) % 4 };
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
    const players: BoardDisplayState["players"] = [playHand(bottom, plays), right, top, left];
    return { ...board, players: markSource(players, kanSource(state)) };
}

function withSource(player: BoardPlayerDisplay, meld: number): BoardPlayerDisplay {
    return { ...player, sourceMeld: meld };
}

/** The players with the kan a chankan offer may rob marked in its declarer's melds; as they were with none. */
function markSource(
    players: BoardDisplayState["players"],
    source: { position: number; meld: number } | null,
): BoardDisplayState["players"] {
    if (source === null) {
        return players;
    }
    const [bottom, right, top, left] = players.map((player, position) =>
        position === source.position ? withSource(player, source.meld) : player,
    );
    return [bottom, right, top, left];
}

/** Whether No calls passed the decision, which then shows nothing: its controls never appear. */
function passedByNoCalls(state: GameClientState): boolean {
    const status = state.decision?.status;
    return status?.kind === "submitted" && status.bySwitch === "no_calls";
}

function decisionStanding(state: GameClientState): DecisionStanding | null {
    return passedByNoCalls(state) ? null : (state.decision?.status.kind ?? null);
}

/** The play switches as the board shows them, each turned by its intent, while the dispatcher takes that. */
function switchControls(state: GameClientState): SwitchControl[] {
    return PLAY_SWITCHES.flatMap((playSwitch): SwitchControl[] => {
        const intent: PlayIntent = { playSwitch, type: "toggle_switch" };
        if (!takesIntent(state, intent)) {
            return [];
        }
        return [
            {
                command: intentCommand(intent),
                label: SWITCH_LABELS[playSwitch],
                on: state.switches[playSwitch],
                playSwitch,
            },
        ];
    });
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
    if (hasLostSeat(session)) {
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
        actions: decisionActions(state, ui),
        board: viewerBoard(state, plays),
        callouts: liveCallouts(state),
        countdown: decisionCountdown(state),
        decisionStanding: decisionStanding(state),
        escape: escapeCommand(state, ui),
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
        switches: switchControls(state),
        tileAction: picking ? RIICHI_ACTION : DISCARD_ACTION,
        tileIntents: intentsOf(plays),
        viewerSeat,
    };
}

/** Whether the open decision was answered, so its steps stay as they were while the server answers. */
function answeredDecision(state: GameClientState): boolean {
    return state.decision?.status.kind === "submitted";
}

/** Picking riichi's discard turned on (for the open decision, closing a choice of tiles) or off. */
function toggledRiichiPick(state: GameClientState, ui: PlayUi): PlayUi {
    if (answeredDecision(state)) {
        return ui;
    }
    const waitId = state.decision?.waitId ?? null;
    const riichiPickWaitId = pickingRiichi(state, ui) ? null : waitId;
    return { ...ui, riichiPickWaitId, tileChoice: null };
}

/** A call's choice of tiles opened (for the open decision, turning the riichi pick off) or closed. */
function toggledTileChoice(state: GameClientState, ui: PlayUi, kind: TileChoiceKind): PlayUi {
    const { decision } = state;
    if (decision === null || answeredDecision(state)) {
        return ui;
    }
    const tileChoice = choosingTiles(state, ui) === kind ? null : { kind, waitId: decision.waitId };
    return { ...ui, riichiPickWaitId: null, tileChoice };
}

/** The view's `ui` after one of the open decision's steps: the riichi toggle, a call's choice of tiles, a step back. */
function steppedDecision(
    state: GameClientState,
    ui: PlayUi,
    command: Extract<
        PlayCommand,
        { kind: "toggle_riichi_pick" | "toggle_tile_choice" | "step_back" }
    >,
): PlayUi {
    if (command.kind === "toggle_riichi_pick") {
        return toggledRiichiPick(state, ui);
    }
    return command.kind === "toggle_tile_choice"
        ? toggledTileChoice(state, ui, command.offer)
        : steppedBack(state, ui);
}

/** One step back: out of a call's choice of tiles, else the riichi pick off. */
function steppedBack(state: GameClientState, ui: PlayUi): PlayUi {
    if (answeredDecision(state)) {
        return ui;
    }
    if (choosingTiles(state, ui) !== null) {
        return { ...ui, tileChoice: null };
    }
    return { ...ui, riichiPickWaitId: null };
}

/** The game's last result reopens on its first page; any other intent leaves the view's `ui` as it was. */
function uiAfterIntent(ui: PlayUi, intent: LocalIntent): PlayUi {
    return intent.type === "show_last_result" ? { ...ui, resultPage: null } : ui;
}

/**
 * The view's `ui` after a command: picking riichi's discard, or choosing a call's tiles, turns on or off for the open
 * decision, each turning the other off, and an answered decision keeps both as they were; stepping back leaves the
 * choice of tiles, else the riichi pick; the result's panel turns to a page of the result showing, and the game's last
 * result reopens on its first; a nameplate is pinned, or none.
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
        case "toggle_riichi_pick":
        case "toggle_tile_choice":
        case "step_back": {
            return steppedDecision(state, ui, command);
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
