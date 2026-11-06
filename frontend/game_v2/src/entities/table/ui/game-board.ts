import { type TemplateResult, html, nothing } from "lit-html";
import { type DirectiveResult } from "lit-html/directive.js";
import { keyed } from "lit-html/directives/keyed.js";
import { styleMap } from "lit-html/directives/style-map.js";

import { SIDEWAYS_UNITS, STACKED_DEPTH, UPRIGHT_DEPTH } from "@/entities/table/lib/board-constants";
import { CALLOUT_MS } from "@/entities/table/lib/callouts";
import { type StripContent } from "@/entities/table/lib/strip-layout";
import {
    type BoardCallout,
    type BoardCallouts,
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardMotionCue,
    type BoardNameplate,
    type BoardPlayerDisplay,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import {
    Discards,
    Hand,
    Meld,
    type MeldTile,
    type RiverOverflow,
    Tile,
    type TileAction,
    TileBack,
} from "@/entities/tile";

import { sizeBoard } from "./board-geometry-directive";
import { animateBoard } from "./board-motion-directive";
import { type BoardNotice, BoardNotices, NoticeAnnouncements } from "./board-notices";
import { HonbaStickIcon } from "./honba-stick-icon";
import { Nameplates, type PlatePress, pinnedPlate } from "./nameplate";
import { fadeMatchResult, revealAfterCall } from "./panel-motion-directive";
import { RiichiStickIcon } from "./riichi-stick-icon";

/** How the bottom seat's hand is played: what a selectable tile does and where its tap goes. */
interface LocalHandInput {
    readonly onTile: (tileId: number) => void;
    readonly tileAction: TileAction;
}

interface GameBoardProps {
    readonly matchResult?: boolean;
    readonly motion?: BoardMotionCue;
    readonly debug: boolean;
    readonly overlay?: TemplateResult;
    readonly state: BoardDisplayState | null;
    /** The decision's controls (its countdown, offers and pass), by the bottom seat's hand. */
    readonly actions?: TemplateResult;
    readonly localHand?: LocalHandInput;
    /** The notices over the table; given, even empty, the board keeps their live region for the next one. */
    readonly notices?: readonly BoardNotice[];
    /** The overlay's panel blocks the board: everything under it takes no input, by keyboard or pointer. */
    readonly inert?: boolean;
    /** What pressing a plate does: pin it to show the others' score differences, or view the table from its seat. */
    readonly platePress: PlatePress;
    /** The page's own controls (the settings: sound and the connection), in the board's top-right corner. */
    readonly menu?: TemplateResult;
    /**
     * The calls shown by their seats for a moment, over the table and never over the local hand; they take no input.
     * Each new announced showing is read out once, by its seats' names.
     */
    readonly callouts?: BoardCallouts | null;
    /** The overlay's panel waits until the win's call shown with it has been seen (a round's result); else it shows at once. */
    readonly overlayAfterCall?: boolean;
    /** The bottom seat is furiten: a played board labels its hand with the mark. */
    readonly furiten?: boolean;
    /** The play switches, in their slot on the foreground band's side away from the decisions. */
    readonly switches?: TemplateResult;
    /**
     * A replay's controls, over the foreground band in the decisions' place, and in the switches' where the band shares
     * the core's corners (a board that shows them plays no hand), and what it shows in the notices' place under any
     * notice (its position).
     */
    readonly replay?: { readonly controls: TemplateResult; readonly status: TemplateResult };
    readonly input?: DirectiveResult;
}

function HandArea(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
    input?: LocalHandInput,
): TemplateResult {
    return html`<div class="board-area board-area--${seat}-hand" data-area="${seat}-hand">
        ${player ? Hand({ drawnTile: player.drawnTile, tiles: player.hand, ...input }) : ""}
    </div>`;
}

/**
 * A seat's melds, newest first from the hand outward, so the first meld lies farthest right; the one an offer refers to
 * marked as its source.
 */
function MeldsArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    const melds = player?.melds ?? [];
    return html`<div class="board-area board-melds board-area--${seat}-melds" data-area="${seat}-melds">
        ${melds.toReversed().map((tiles, index) => Meld(tiles, melds.length - 1 - index === player?.sourceMeld))}
    </div>`;
}

/** Each seat's river past its third row: a side river wraps toward its seat's edge, a top or bottom one runs on. */
const RIVER_OVERFLOW: Readonly<Record<SeatPosition, RiverOverflow>> = {
    bottom: "run-on",
    left: "wrap",
    right: "wrap",
    top: "run-on",
};

/**
 * A seat's river: its area the turned footprint of a normal river at its place in the pinwheel, its frame turned to the
 * seat from the area's corner where the first row starts.
 */
function River(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-area board-river board-river--${seat}" data-area="${seat}-discards">
        <div class="board-river__frame">${player ? Discards(player.discards, RIVER_OVERFLOW[seat]) : ""}</div>
    </div>`;
}

const STRIP_SEATS: readonly SeatPosition[] = ["right", "top", "left"];

/** How long a laid meld is, in its tiles' widths: a sideways or stacked tile lies as long as a tile is tall. */
function meldUnits(tiles: readonly MeldTile[]): number {
    return tiles.reduce(
        (sum, tile) =>
            sum + (tile.kind === "sideways" || tile.kind === "stacked" ? SIDEWAYS_UNITS : 1),
        0,
    );
}

/** How deep a laid meld stands from its seat's edge, in its tiles' widths: an added kan's stack is two tiles deep. */
function meldDepth(tiles: readonly MeldTile[]): number {
    return tiles.some((tile) => tile.kind === "stacked") ? STACKED_DEPTH : UPRIGHT_DEPTH;
}

/** What an opponent's strip is laid out from: its hand's tiles, whether one is drawn apart, its melds newest first. */
function stripContent(player: BoardPlayerDisplay | null): StripContent {
    const drawn = player?.drawnTile !== undefined;
    return {
        drawn,
        hand: (player?.hand.length ?? 0) + (drawn ? 1 : 0),
        melds: (player?.melds ?? [])
            .toReversed()
            .map((tiles) => ({ depth: meldDepth(tiles), units: meldUnits(tiles) })),
    };
}

function seatPlayer(
    state: BoardDisplayState | null,
    seat: SeatPosition,
): BoardPlayerDisplay | null {
    return state?.players[SEAT_POSITIONS.indexOf(seat)] ?? null;
}

/** What the own row's melds scale from to end before the board's edge: how many there are and how long, in tiles. */
function ownMeldStyle(player: BoardPlayerDisplay | null): Readonly<Record<string, string>> {
    const melds = player?.melds ?? [];
    return {
        "--meld-n": String(melds.length),
        "--meld-units": String(melds.reduce((sum, tiles) => sum + meldUnits(tiles), 0)),
    };
}

/** The own row's badge and the hand's input, which only the bottom seat's strip holds. */
interface OwnRow {
    readonly head: TemplateResult | "";
    readonly input?: LocalHandInput;
}

/**
 * A seat's strip: its hand, then its melds newest first from the hand outward. An opponent's stands in its area, its
 * frame turned to its seat from the area's corner at its hand's start, its melds in one line at `stripLayout`'s shared scale; the own row stands in the hand's slot, its melds scaled to
 * end before the board's edge.
 */
function Strip(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
    own?: OwnRow,
): TemplateResult {
    if (seat === "bottom") {
        return html`<div class="board-local" style=${styleMap(ownMeldStyle(player))}>
            ${own?.head ?? ""}${HandArea(seat, player, own?.input)}${MeldsArea(seat, player)}
        </div>`;
    }
    return html`<div class="board-strip board-strip--${seat}">
        <div class="board-strip__frame">${HandArea(seat, player)}${MeldsArea(seat, player)}</div>
    </div>`;
}

/** The faint lines from the centre's corners and the side fields' tint that make the four zones perceptible. */
function Zones(): TemplateResult {
    return html`<div class="board-zones" aria-hidden="true">
        <span class="board-zones__field board-zones__field--left"></span>
        <span class="board-zones__field board-zones__field--right"></span>
        <span class="board-zones__field board-zones__field--top"></span>
        <span class="board-zones__line board-zones__line--top-left"></span>
        <span class="board-zones__line board-zones__line--top-right"></span>
        <span class="board-zones__line board-zones__line--bottom-right"></span>
        <span class="board-zones__line board-zones__line--bottom-left"></span>
    </div>`;
}

const DORA_SLOTS = 5;

/**
 * The pooled counters: the dora indicators turned so far, a back in each slot still to turn, and the table's honba and
 * riichi sticks as icon and number, which the centre does not repeat.
 */
function DoraDisplay(center: BoardCenterInfo): TemplateResult {
    const indicators = center.doraIndicators;
    const backs = Math.max(0, DORA_SLOTS - indicators.length);
    return html`
        <div class="board-dora">
            <div class="board-dora__tiles" role="group" aria-label="Dora indicators">
                ${indicators.map((face) => html`<span class="board-dora__tile">${Tile(face, "face")}</span>`)}
                ${Array.from({ length: backs }, () => html`<span class="board-dora__tile">${TileBack()}</span>`)}
            </div>
        </div>
    `;
}

/** A score in hundreds with its last two digits apart, as Tenhou draws it (`250` `00`); a score is whole hundreds. */
function ScoreFigures(score: string): TemplateResult {
    const split = /^(?<hundreds>[+-]?\d+)00$/u.exec(score);
    return split?.groups === undefined
        ? html`${score}`
        : html`${split.groups.hundreds}<span class="board-center__hundreds">00</span>`;
}

/**
 * A seat's side of the centre, turned to face it: its wind (the dealer's, East, on a muted red chip) and score, or while a plate is
 * hovered or pinned (or the centre, standing for the bottom plate, is hovered) its difference from that plate's seat, and above them its riichi stick once its riichi stands. A
 * bar along its edge marks whose turn it is. Where pressing a plate views from its seat, so does a pointer's press of
 * another seat's score; the keyboard's is the plate's.
 */
function CenterSeat(
    plate: BoardNameplate,
    position: SeatPosition,
    onView: ((seat: SeatPosition) => void) | null,
): TemplateResult {
    const classes = [
        "board-center__seat",
        `board-center__seat--${position}`,
        plate.isCurrent ? "board-center__seat--current" : "",
        plate.isDealer ? "board-center__seat--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");
    const diffs = SEAT_POSITIONS.filter((other) => other !== position).map(
        (other) =>
            html`<span class="board-center__diff board-center__diff--${other}"
                >${ScoreFigures(plate.scoreDiffs[other])}</span
            >`,
    );
    const viewable = onView !== null && position !== "bottom";
    return html`<div class=${classes}>
        <span class="board-center__riichi ${plate.isRiichi ? "" : "board-center__riichi--none"}"></span>
        <span
            class="board-center__score-line ${viewable ? "board-center__score-line--view" : ""}"
            title=${viewable ? `View from ${plate.name}` : nothing}
            @click=${viewable ? () => onView(position) : nothing}
            ><span class="board-center__wind">${plate.wind}</span
            ><span class="board-center__score">${ScoreFigures(plate.score)}</span>${diffs}</span
        >
    </div>`;
}

/**
 * While a badge's differences show, the label naming whose they are, beside the wall's count, which stays: one per
 * seat, which the board's stylesheet shows for the hovered or pinned badge, naming the seat whole where its name fits
 * the line, else by its wind, which assistive technology skips for the whole name.
 */
function DiffLabels(plates: BoardDisplayState["nameplates"]): TemplateResult {
    return html`${SEAT_POSITIONS.map(
        (position, index) =>
            html`<div class="board-center__diff-label board-center__diff-label--${position}">
                <span class="board-center__diff-vs">vs</span>
                <span class="board-center__diff-slot"
                    ><span class="board-center__diff-names"
                        ><span class="board-center__diff-name">${plates[index].name}</span
                        ><span class="board-center__diff-wind" aria-hidden="true">${plates[index].windName}</span></span
                    ></span
                >
            </div>`,
    )}`;
}

/**
 * The centre: each seat's wind and score on its side, its riichi stick inside the edge, the turn's bar on it, and in
 * its middle the round over the wall's count and the honba and riichi sticks on the table, as Tenhou's.
 */
function CenterInfo(
    center: BoardCenterInfo,
    plates: BoardDisplayState["nameplates"],
    press: PlatePress,
): TemplateResult {
    const onView = press.kind === "view" ? press.onView : null;
    return html`
        <div class="board-area board-center" data-area="center">
            ${SEAT_POSITIONS.map((position, index) => CenterSeat(plates[index], position, onView))}
            <div class="board-center__info">
                <div class="board-center__round">${center.roundDisplay}</div>
                <div class="board-center__counts">
                    <span class="board-center__count board-center__count--wall" title="Tiles left in the wall"
                        ><span class="board-center__label">Wall </span
                        ><span class="board-center__figure">${center.tilesRemaining}</span></span
                    >
                    <span class="board-center__sticks">
                        <span class="board-center__count" title="Honba"
                            >${HonbaStickIcon()}<span class="board-center__label">Honba </span
                            ><span class="board-center__figure">${center.honbaSticks}</span></span
                        >
                        <span class="board-center__count" title="Riichi sticks on the table"
                            >${RiichiStickIcon()}<span class="board-center__label">Riichi sticks </span
                            ><span class="board-center__figure">${center.riichiSticks}</span></span
                        >
                    </span>
                </div>
                ${DiffLabels(plates)}
            </div>
        </div>
    `;
}

/**
 * Where a call's chip lies over its caller's river, in the river's frame (along its rows in river tiles, away from the
 * centre in river rows): a top or bottom river's chip centred along its rows; a side river's, upright and wider than
 * the river, from its outer edge inward, clear of the decisions beside it.
 */
const CALLOUT_SPOTS: Readonly<Record<SeatPosition, readonly [number, number]>> = {
    bottom: [3, 1.5],
    left: [3, 4],
    right: [3, 4],
    top: [3, 2.5],
};

function Callout({ kind, label, position }: BoardCallout): TemplateResult {
    const [along, across] = CALLOUT_SPOTS[position];
    return html`<div
        class="board-callout board-callout--${position} board-callout--${kind}"
        style="--spot-along: ${along}; --spot-across: ${across}"
    >
        <span class="board-callout__word">${label}</span>
    </div>`;
}

/**
 * The calls by their seats, each over its caller's river; a new showing (a new key) is drawn afresh, so its animation
 * plays from the start, over the time a call shows.
 */
function Callouts(callouts: BoardCallouts): TemplateResult {
    return html`${keyed(
        callouts.key,
        html`<div class="board-callouts" style="--callout-ms: ${CALLOUT_MS}ms" aria-hidden="true">${callouts.items.map(
            (item) => Callout(item),
        )}</div>`,
    )}`;
}

/** What a showing of calls reads out: each caller's name and call, `Bob: Pon`. */
function calloutWords(callouts: BoardCallouts, state: BoardDisplayState | null): string {
    return callouts.items
        .map(({ label, position }) => {
            const name = state?.nameplates[SEAT_POSITIONS.indexOf(position)].name;
            return name === undefined ? label : `${name}: ${label}`;
        })
        .join(", ");
}

/**
 * The calls as a polite live region of their own, each announced showing read once: a new showing is a new key, a
 * redraw none.
 */
function CalloutAnnouncements(
    callouts: BoardCallouts | null | undefined,
    state: BoardDisplayState | null,
): TemplateResult {
    return html`<div
        class="board-announce board-announce--calls"
        aria-live="polite"
        aria-atomic="false"
        aria-relevant="additions"
    >${
        callouts?.announced === true
            ? keyed(callouts.key, html`<p>${calloutWords(callouts, state)}</p>`)
            : nothing
    }</div>`;
}

/** The own badge over the hand's left end, and the furiten mark beside it while the seat is furiten. */
function OwnHead(plate: TemplateResult, furiten: boolean): TemplateResult {
    return html`<div class="board-own-head">${plate}${furiten ? FuritenMark() : ""}</div>`;
}

/** The furiten mark, a small label beside the own badge: a dot and the word. */
function FuritenMark(): TemplateResult {
    return html`<span class="board-furiten" title="Furiten: you cannot win on a discard"
        ><span class="board-furiten__dot" aria-hidden="true"></span
        ><span class="board-furiten__word">Furiten</span></span
    >`;
}

function EmptyCenterArea(): TemplateResult {
    return html`
        <div class="board-area board-center" data-area="center"></div>
    `;
}

/**
 * The board, sized from its own box (docs/game-client-look.md, Composition): the core of the centre and the four
 * rivers in their pinwheel, the other seats' strips and badges in their zones toward the edges, the pooled counters in
 * the top-left corner and the page's own controls (`menu`) in the top-right, and over the foreground band the bottom
 * seat's badge, hand and melds with the decision's controls and the play switches, when given, by the hand; a board
 * the viewer plays (`localHand`) also marks its badge furiten while it is. A pinned badge unpins on a click anywhere else on
 * the board or on Escape (a replay's badges pin nothing: pressing one, or another seat's score, views from its seat); with none pinned, Escape steps back from a decision's step. Calls show over their seats' rivers for a
 * moment, clear of the latest discard, and a win's call shows before the panel over the board does.
 */
function GameBoard(props: GameBoardProps): TemplateResult {
    const { platePress, state } = props;
    const pinned = pinnedPlate(platePress);
    const boardClass = [
        "game-board",
        props.localHand ? "game-board--play" : "",
        props.replay ? "game-board--replay" : "",
        import.meta.env.DEV && props.debug ? "game-board--debug" : "",
        pinned === null ? "" : `game-board--diff-${pinned}`,
    ]
        .filter(Boolean)
        .join(" ");
    const bandEnd = props.actions ?? props.replay?.controls;
    const bottom = state?.players[0] ?? null;
    const plates = state ? Nameplates(state.nameplates, platePress) : null;
    function unpinOnClickElsewhere(event: MouseEvent): void {
        const { target } = event;
        const onPlate = target instanceof Element && target.closest(".nameplate") !== null;
        if (platePress.kind === "pin" && pinned !== null && !onPlate) {
            platePress.onPin(null);
        }
    }
    function onKey(event: KeyboardEvent): void {
        if (props.input !== undefined || event.key !== "Escape" || event.defaultPrevented) {
            return;
        }
        if (platePress.kind === "pin" && pinned !== null) {
            platePress.onPin(null);
            return;
        }
    }

    return html`
        <div
            class="${boardClass}"
            ${props.input ?? nothing}
            ${sizeBoard(
                { band: props.replay ? "replay" : "play" },
                {
                    left: stripContent(seatPlayer(state, "left")),
                    right: stripContent(seatPlayer(state, "right")),
                    top: stripContent(seatPlayer(state, "top")),
                },
            )}
            ${animateBoard(state, props.motion)}
            ${fadeMatchResult(props.matchResult === true)}
            @click=${unpinOnClickElsewhere}
            @keydown=${onKey}
        >
            <div class="board-layout" ?inert=${props.inert ?? false}>
                ${Zones()}
                <div class="board-table">
                    <div class="board-rivers">
                        ${SEAT_POSITIONS.map((seat, i) => River(seat, state?.players[i] ?? null))}
                    </div>
                    ${state ? CenterInfo(state.center, state.nameplates, platePress) : EmptyCenterArea()}
                    ${STRIP_SEATS.map((seat) => Strip(seat, seatPlayer(state, seat)))}
                    ${state ? DoraDisplay(state.center) : ""}
                    ${plates ? html`${plates.right}${plates.top}${plates.left}` : ""}
                    ${props.menu ? html`<div class="board-menu">${props.menu}</div>` : ""}
                    ${bandEnd ? html`<div class="board-actions" data-area="actions">${bandEnd}</div>` : ""}
                    ${props.switches ?? ""}
                    ${props.notices || props.replay ? BoardNotices(props.notices ?? [], props.replay?.status) : ""}
                    ${props.callouts ? Callouts(props.callouts) : ""}
                </div>
                ${Strip("bottom", bottom, {
                    head: plates
                        ? OwnHead(
                              plates.bottom,
                              props.localHand !== undefined && props.furiten === true,
                          )
                        : "",
                    ...(props.localHand ? { input: props.localHand } : {}),
                })}
            </div>
            ${props.notices ? NoticeAnnouncements(props.notices) : ""}
            ${CalloutAnnouncements(props.callouts, state)}
            ${
                props.overlay
                    ? html`<div class="board-overlay" ${revealAfterCall(props.overlayAfterCall === true)}>
                      <div class="board-overlay__panel" data-board-panel>${props.overlay}</div>
                  </div>`
                    : ""
            }
        </div>
    `;
}

export { GameBoard };
export type { GameBoardProps, LocalHandInput };
