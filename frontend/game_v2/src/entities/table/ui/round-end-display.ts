import { type TemplateResult, html, nothing } from "lit-html";

import {
    type DrawPageDisplay,
    type NagashiPageDisplay,
    type ResultHandDisplay,
    type ResultSeat,
    type ResultSticks,
    type ResultYakuLine,
    type RoundEndDisplayState,
    type WinBodyDisplay,
    type WinPageDisplay,
    formatDelta,
    formatPoints,
} from "@/entities/table/lib/round-end-display";
import { Hand, Meld, Tile, TileBack, type TileFace } from "@/entities/tile";
import { t } from "@/shared/i18n";
import { assertNever } from "@/shared/lib";

import { PANEL_CONTROL_FOCUS_KEY } from "./focus";
import { HonbaStickIcon } from "./honba-stick-icon";
import { peekWhilePressed } from "./panel-peek-directive";
import { PlayerName } from "./player-name";
import { RiichiStickIcon } from "./riichi-stick-icon";

/** The dead wall's indicator row: five slots, the revealed indicators first and the rest face down. */
const DEAD_WALL_SLOTS = 5;

/** How the shown win was made, as the seats' tags say it: Ron or Tsumo, who won and who dealt in. */
interface ShownWin {
    readonly word: string;
    readonly winnerSeat: number;
    readonly fromSeat: number | null;
}

interface SeatMark {
    readonly label: string;
    readonly kind: "winner" | "dealt";
}

export interface RoundEndDisplayProps {
    readonly display: RoundEndDisplayState;
    /** Called with the page to show; without it the panel offers no paging, only says which page it shows. */
    readonly onPage?: (page: number) => void;
    /**
     * The viewer's controls in the diamond's bottom-right corner, toward the thumb (the live game's Next and confirm):
     * its primary action. Without them a result of several pages offers its own Next there.
     */
    readonly controls?: TemplateResult;
}

function shownWin(display: RoundEndDisplayState): ShownWin | null {
    const { body } = display;
    if (body.kind !== "win") {
        return null;
    }
    const page = body.pages[display.page];
    if (page === undefined) {
        throw new Error(`no win page ${display.page}`);
    }
    return { fromSeat: page.fromSeat, winnerSeat: page.winnerSeat, word: page.winningTileLabel };
}

function Melds(melds: ResultHandDisplay["melds"]): TemplateResult | typeof nothing {
    if (melds.length === 0) {
        return nothing;
    }
    return html`<span class="round-end-result__melds">${melds.map((meld) => Meld(meld))}</span>`;
}

/** The winner's closed tiles, then the winning tile set apart, then the melds. */
function WinHand(page: WinPageDisplay): TemplateResult {
    return html`<div class="round-end-result__hand">
        ${Hand({ tiles: page.hand.tiles })}
        <span class="round-end-result__win-tile" role="group" aria-label=${page.winningTileLabel}
            >${Hand({ tiles: [page.winningTile] })}</span
        >
        ${Melds(page.hand.melds)}
    </div>`;
}

function DeadWallRow(label: string, faces: readonly TileFace[]): TemplateResult {
    const backs = Math.max(0, DEAD_WALL_SLOTS - faces.length);
    return html`<span class="round-end-result__wall-row" role="group" aria-label=${label}
        >${faces.map((face) => Tile(face, "face"))}${Array.from(
            { length: backs },
            () => html`<span class="round-end-result__wall-back">${TileBack()}</span>`,
        )}</span
    >`;
}

/** The indicators as the dead wall shows them, the ura row under the dora's once the winner's riichi revealed it. */
function Indicators(page: WinPageDisplay): TemplateResult {
    return html`<div class="round-end-result__wall" role="group" aria-label=${t("game.result.indicators")}>
        ${DeadWallRow(t("yaku.120"), page.doraIndicators)}
        ${page.uraIndicators.length === 0 ? nothing : DeadWallRow(t("game.result.ura"), page.uraIndicators)}
    </div>`;
}

/** A yakuman's caption: its translated name, kept for a screen reader alone where the kanji already show it. */
function YakumanCaption(name: string, multiple: string | null, shown: boolean): TemplateResult {
    const named = shown
        ? name
        : html`<span class="round-end-result__yakuman-name-heard">${name}</span>`;
    const separator = shown ? " · " : " ";
    return html`<span class="round-end-result__yakuman-name"
        >${named}${multiple === null ? nothing : `${separator}${multiple}`}</span
    >`;
}

/**
 * A named yakuman as a seal: its stamp, its name in kanji large, and its translated name under it where that differs
 * (a Japanese page shows the kanji alone). The stamp and kanji are its look; a screen reader reads the name.
 */
function YakumanLine(
    line: ResultYakuLine,
    yakuman: NonNullable<ResultYakuLine["yakuman"]>,
): TemplateResult {
    const kanji = yakuman.kanji ?? line.name;
    return html`<li class="round-end-result__yakuman">
        <span class="round-end-result__seal" aria-hidden="true" lang="ja">${yakuman.seal}</span>
        <span class="round-end-result__yakuman-text">
            <span class="round-end-result__yakuman-kanji" lang="ja" aria-hidden="true">${kanji}</span>
            ${YakumanCaption(line.name, yakuman.multiple, kanji !== line.name)}
        </span>
    </li>`;
}

function YakuLine(line: ResultYakuLine): TemplateResult {
    if (line.yakuman !== null) {
        return YakumanLine(line, line.yakuman);
    }
    return html`<li>
        <span class="round-end-result__yaku-name">${line.name}</span>
        ${line.han === null ? nothing : html`<span class="round-end-result__han">${line.han}</span>`}
    </li>`;
}

/** The honba and riichi sticks the winner collected, as counts; their place stays reserved at none. */
function Sticks(sticks: ResultSticks): TemplateResult {
    const hidden = sticks.bonus === 0;
    return html`<span class="round-end-result__sticks" aria-hidden=${hidden ? "true" : "false"}>
        ${
            sticks.honba === null
                ? nothing
                : html`<span class="round-end-result__stick" title=${t("game.board.honba")}
                      >${HonbaStickIcon()}<span class="round-end-result__stick-label">${t("game.board.honba")} </span
                      >${sticks.honba}</span
                  >`
        }
        <span class="round-end-result__stick" title=${t("game.board.riichi_sticks")}
            >${RiichiStickIcon()}<span class="round-end-result__stick-label">${t("game.board.riichi_sticks")} </span
            >${sticks.riichi}</span
        >
    </span>`;
}

function Value(limit: string | null, points: number | null): TemplateResult {
    return html`<div class="round-end-result__value">
        ${limit === null ? nothing : html`<span class="round-end-result__limit">${limit}</span>`}
        ${points === null ? nothing : html`<span class="round-end-result__points">${formatPoints(points)}</span>`}
    </div>`;
}

/** One column read down: the yaku, then the dora, scrolling where long; the yaku resting on the total and value. */
function Scoring(page: WinPageDisplay): TemplateResult {
    const yaku = page.yaku.filter((line) => !line.isDora);
    const dora = page.yaku.filter((line) => line.isDora);
    return html`<div class="round-end-result__scoring">
        <div class="round-end-result__yaku-scroll">
            <ul class="round-end-result__yaku">${yaku.map(YakuLine)}</ul>
            ${
                dora.length === 0
                    ? nothing
                    : html`<ul class="round-end-result__yaku round-end-result__yaku--dora">${dora.map(YakuLine)}</ul>`
            }
        </div>
        <div class="round-end-result__total">
            ${page.hanFu === null ? nothing : html`<div class="round-end-result__han-fu">${page.hanFu}</div>`}
            ${Value(page.limit, page.points)}
            ${page.notes.map((note) => html`<div class="round-end-result__note">${note}</div>`)}
        </div>
    </div>`;
}

function Seat(seat: ResultSeat, mark: SeatMark | null): TemplateResult {
    const zero = seat.delta === 0;
    const marked = mark === null ? "" : ` round-end-result__seat--${mark.kind}`;
    return html`<div
        class="round-end-result__seat round-end-result__seat--${seat.position} round-end-result__seat--${seat.role}${marked}"
    >
        ${mark === null ? nothing : html`<span class="round-end-result__seat-mark">${mark.label}</span>`}
        <div class="round-end-result__seat-name">
            <span class="round-end-result__score-wind"
                ><span aria-hidden="true">${seat.wind}</span
                ><span class="round-end-result__score-wind-name">${seat.windName}</span></span
            >
            ${PlayerName(seat.name, "round-end-result__score-name")}
            ${seat.tag === null ? nothing : html`<span class="round-end-result__score-tag">${seat.tag}</span>`}
        </div>
        <div class="round-end-result__seat-figures">
            <span class="round-end-result__delta" aria-hidden=${zero ? "true" : "false"}
                >${zero ? "0" : formatDelta(seat.delta)}</span
            >
            <span class="round-end-result__standing"
                ><span class="round-end-result__score-after">${formatPoints(seat.after)}</span>
                <span class="round-end-result__rank">${seat.rank}</span></span
            >
        </div>
    </div>`;
}

function PageButton(
    props: RoundEndDisplayProps,
    page: number,
    direction: "previous" | "next",
): TemplateResult | typeof nothing {
    const name = props.display.pageNames[page];
    const { onPage } = props;
    if (onPage === undefined || name === undefined) {
        return nothing;
    }
    const shownName = html`<span class="round-end-result__page-name">${name}</span>`;
    const label =
        direction === "previous"
            ? html`<span aria-hidden="true">&lsaquo;</span>${shownName}`
            : html`${shownName}<span aria-hidden="true">&rsaquo;</span>`;
    const classes =
        direction === "previous"
            ? "round-end-result__prev outline secondary"
            : "round-end-result__next";
    return html`<button
        type="button"
        class=${classes}
        data-focus-key=${PANEL_CONTROL_FOCUS_KEY}
        aria-label=${t("game.result.show_winner", { name })}
        @click=${(event: Event) => {
            onPage(page);
            if (event.currentTarget instanceof HTMLElement) {
                keepPagingFocus(event.currentTarget, direction);
            }
        }}
    >${label}</button>`;
}

const PRIMARY_CONTROLS =
    ".round-end-result__next, .round-end-result__confirm:not(.round-end-result__ghost)";
const PREVIOUS_CONTROL = ".round-end-result__prev";

/**
 * A page button that its own press removed (the previous winner's on reaching the first page, a Next on reaching the
 * last) hands the focus it held to the control that turns the pages the other way, else the corner's primary, once
 * the page has drawn; a focus another control took meanwhile is left alone.
 */
function keepPagingFocus(button: HTMLElement, direction: "previous" | "next"): void {
    const settle = button.closest(".round-end-result__settle");
    const order =
        direction === "previous"
            ? [PRIMARY_CONTROLS, PREVIOUS_CONTROL]
            : [PREVIOUS_CONTROL, PRIMARY_CONTROLS];
    requestAnimationFrame(() => {
        const focused = button.ownerDocument.activeElement;
        if (button.isConnected || settle === null || !settle.isConnected) {
            return;
        }
        if (focused instanceof HTMLButtonElement && focused.isConnected) {
            return;
        }
        const target = order
            .map((selector) => settle.querySelector<HTMLElement>(selector))
            .find((control) => control !== null);
        target?.focus({ preventScroll: true });
    });
}

/**
 * The bottom-right corner: the viewer's controls when it has any, else a Next to the following page, else, for a
 * panel that cannot page, which page it shows.
 */
function Primary(props: RoundEndDisplayProps): TemplateResult | typeof nothing {
    const { controls, display, onPage } = props;
    if (controls !== undefined) {
        return controls;
    }
    if (onPage === undefined && display.pageCount > 1) {
        return html`<span class="round-end-result__page">${display.page + 1} / ${display.pageCount}</span>`;
    }
    if (display.page >= display.pageCount - 1) {
        return nothing;
    }
    return PageButton(props, display.page + 1, "next");
}

/**
 * The seats where they sit at the table, the bottom seat at the bottom, with the round between them like the board's
 * centre, and the ways between pages and on in the corners under them.
 */
/** A win's tags: Ron or Tsumo on the winner's card, Dealt in on the card of the seat it was won from. */
function seatMark(seat: ResultSeat, win: ShownWin | null): SeatMark | null {
    if (win === null) {
        return null;
    }
    if (seat.seat === win.winnerSeat) {
        return { kind: "winner", label: win.word };
    }
    if (seat.seat === win.fromSeat) {
        return { kind: "dealt", label: t("game.result.dealt_in") };
    }
    return null;
}

function Settlement(
    props: RoundEndDisplayProps,
    centre: TemplateResult | typeof nothing = nothing,
): TemplateResult {
    const { display } = props;
    const win = shownWin(display);
    return html`<div class="round-end-result__settle">
        ${display.seats.map((seat) => Seat(seat, seatMark(seat, win)))}
        <div class="round-end-result__centre">
            ${display.round === null ? nothing : html`<div class="round-end-result__round">${display.round}</div>`}
            ${centre}
        </div>
        ${display.page > 0 ? PageButton(props, display.page - 1, "previous") : nothing}
        ${Primary(props)}
    </div>`;
}

/** Every page's part stacked in one cell, the shown one visible, so the panel keeps its size as the pages turn. */
function Stack(area: string, layers: readonly TemplateResult[], shown: number): TemplateResult {
    return html`<div class="round-end-result__stack round-end-result__stack--${area}">
        ${layers.map(
            (layer, index) =>
                html`<div class="round-end-result__layer" aria-hidden=${index === shown ? "false" : "true"}>${layer}</div>`,
        )}
    </div>`;
}

/** How the shown win was made, for a screen reader: the seats' changes show it on the screen. */
function WinSummary(page: WinPageDisplay): TemplateResult {
    return html`<div class="round-end-result__head round-end-result__head--hidden">
        <span class="round-end-result__kind">${page.title}</span>
        <span class="round-end-result__winner">${page.winnerName}</span>
        ${page.from === null ? nothing : html`<span class="round-end-result__from">${page.from}</span>`}
    </div>`;
}

function WinResult(props: RoundEndDisplayProps, body: WinBodyDisplay): TemplateResult {
    const { page } = props.display;
    const shown = body.pages[page];
    return html`<div class="round-end-result round-end-result--win" ${peekWhilePressed()}>
        ${shown === undefined ? nothing : WinSummary(shown)}
        ${Stack("hand", body.pages.map(WinHand), page)}
        ${Stack("dora", body.pages.map(Indicators), page)}
        ${Stack("scoring", body.pages.map(Scoring), page)}
        ${Settlement(
            props,
            Stack(
                "sticks",
                body.pages.map(({ sticks }) => Sticks(sticks)),
                page,
            ),
        )}
    </div>`;
}

function NagashiResult(props: RoundEndDisplayProps, body: NagashiPageDisplay): TemplateResult {
    const several = body.makers.length > 1;
    return html`<div class="round-end-result round-end-result--nagashi" ${peekWhilePressed()}>
        <div class="round-end-result__scoring">
            <div class="round-end-result__yaku-scroll">
                <ul class="round-end-result__yaku">
                    <li><span class="round-end-result__yaku-name">${body.title}</span></li>
                    ${
                        several
                            ? body.makers.map(
                                  (name) =>
                                      html`<li><span class="round-end-result__yaku-name">${name}</span></li>`,
                              )
                            : nothing
                    }
                </ul>
            </div>
            <div class="round-end-result__total">
                ${Value(body.limit, body.points)}
            </div>
        </div>
        ${Settlement(props)}
    </div>`;
}

function DrawResult(props: RoundEndDisplayProps, page: DrawPageDisplay): TemplateResult {
    const noHands = page.hands.length === 0 ? " round-end-result--no-hands" : "";
    return html`<div class="round-end-result round-end-result--draw${noHands}" ${peekWhilePressed()}>
        <div class="round-end-result__head">
            <span class="round-end-result__title">${page.title}</span>
            ${page.subtitle === null ? nothing : html`<span class="round-end-result__from">${page.subtitle}</span>`}
        </div>
        ${
            page.hands.length === 0
                ? nothing
                : html`<ul class="round-end-result__tenpai">
                      ${page.hands.map(
                          (shown) => html`<li class="round-end-result__tenpai-hand">
                              <span class="round-end-result__label">${shown.name}</span>
                              <span class="round-end-result__tenpai-tiles"
                                  >${Hand({ tiles: shown.hand.tiles })}${Melds(shown.hand.melds)}</span
                              >
                          </li>`,
                      )}
                  </ul>`
        }
        ${Settlement(props)}
    </div>`;
}

/**
 * A round's result, as `roundEndDisplay` maps it: a win's hand, indicators and scoring column beside the seats where
 * they sit, a nagashi mangan's value, or the draw with its tenpai hands. Given `onPage`, a result of several pages (a
 * double ron's) pages between them, every page's parts kept in place so nothing moves as they turn.
 */
function RoundEndDisplay(props: RoundEndDisplayProps): TemplateResult {
    const { body } = props.display;
    switch (body.kind) {
        case "win": {
            return WinResult(props, body);
        }
        case "nagashi": {
            return NagashiResult(props, body);
        }
        case "draw": {
            return DrawResult(props, body);
        }
        default: {
            return assertNever(body);
        }
    }
}

export { RoundEndDisplay };
