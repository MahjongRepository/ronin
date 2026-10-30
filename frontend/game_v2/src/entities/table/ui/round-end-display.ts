import { type TemplateResult, html, nothing } from "lit-html";

import {
    type DrawPageDisplay,
    type ResultHandDisplay,
    type ResultScoreRow,
    type RoundEndDisplayState,
    type WinPageDisplay,
    formatDelta,
    formatPoints,
} from "@/entities/table/lib/round-end-display";
import { Hand, Meld, Tile, type TileFace } from "@/entities/tile";

import { PlayerName } from "./player-name";

export interface RoundEndDisplayProps {
    readonly display: RoundEndDisplayState;
    /** Called with the page to show; without it the panel offers no paging, only says which page it shows. */
    readonly onPage?: (page: number) => void;
    /** The viewer's controls at the panel's foot, toward the thumb (the live game's confirm): its primary action. */
    readonly controls?: TemplateResult;
}

function deltaModifier(delta: number): string {
    if (delta > 0) {
        return "round-end-result__delta--positive";
    }
    if (delta < 0) {
        return "round-end-result__delta--negative";
    }
    return "";
}

function Melds(melds: ResultHandDisplay["melds"]): TemplateResult | typeof nothing {
    if (melds.length === 0) {
        return nothing;
    }
    return html`<span class="round-end-result__melds">${melds.map((meld) => Meld(meld))}</span>`;
}

function TenpaiHand(name: string, hand: ResultHandDisplay): TemplateResult {
    return html`<li class="round-end-result__tenpai-hand">
        <span class="round-end-result__label">${name}</span>
        <span class="round-end-result__hand">${Hand({ tiles: hand.tiles })}${Melds(hand.melds)}</span>
    </li>`;
}

/** The winner's closed tiles, then the winning tile set apart under its label, then the melds. */
function WinHand(page: WinPageDisplay): TemplateResult {
    return html`<div class="round-end-result__hand">
        ${Hand({ tiles: page.hand.tiles })}
        <span class="round-end-result__win-tile">
            <span class="round-end-result__win-label">${page.winningTileLabel}</span>
            ${Hand({ tiles: [page.winningTile] })}
        </span>
        ${Melds(page.hand.melds)}
    </div>`;
}

function IndicatorGroup(
    label: string,
    faces: readonly TileFace[],
): TemplateResult | typeof nothing {
    if (faces.length === 0) {
        return nothing;
    }
    return html`<div class="round-end-result__indicator-group">
        <span class="round-end-result__label">${label}</span>
        <span class="round-end-result__indicator-tiles">${faces.map((face) => Tile(face, "face"))}</span>
    </div>`;
}

/**
 * The page label, with buttons to turn the page given `onPage`. Beside the viewer's controls they are secondary, an
 * outline, since the controls hold the panel's one primary button (the live game's Next, then its confirm).
 */
function PagerControls({
    controls,
    display,
    onPage,
}: RoundEndDisplayProps): TemplateResult | typeof nothing {
    const { page, pageCount } = display;
    if (pageCount < 2) {
        return nothing;
    }
    const label = html`<span class="round-end-result__page">${page + 1} / ${pageCount}</span>`;
    if (onPage === undefined) {
        return label;
    }
    const buttonClass = `round-end-result__page-btn${controls === undefined ? "" : " outline secondary"}`;
    return html`<span class="round-end-result__pager">
        <button
            class=${buttonClass}
            aria-label="Previous winner"
            ?disabled=${page === 0}
            @click=${() => onPage(page - 1)}
        >&lsaquo;</button>
        ${label}
        <button
            class=${buttonClass}
            aria-label="Next winner"
            ?disabled=${page >= pageCount - 1}
            @click=${() => onPage(page + 1)}
        >&rsaquo;</button>
    </span>`;
}

function YakuList(page: WinPageDisplay): TemplateResult {
    return html`<ul class="round-end-result__yaku">
        ${page.yaku.map(
            (line) => html`<li class=${line.isDora ? "round-end-result__yaku-dora" : ""}>
                <span>${line.name}</span>
                ${line.han === null ? nothing : html`<span class="round-end-result__han">${line.han}</span>`}
                ${line.yakuman === null ? nothing : html`<span class="round-end-result__yakuman">${line.yakuman}</span>`}
            </li>`,
        )}
    </ul>`;
}

function WinValue(page: WinPageDisplay): TemplateResult {
    return html`<div class="round-end-result__value">
        <div class="round-end-result__points">${formatPoints(page.points)}</div>
        ${page.limit === null ? nothing : html`<div class="round-end-result__limit">${page.limit}</div>`}
        ${page.hanFu === null ? nothing : html`<div class="round-end-result__han-fu">${page.hanFu}</div>`}
        <div class="round-end-result__indicators">
            ${IndicatorGroup("Dora", page.doraIndicators)}
            ${IndicatorGroup("Ura", page.uraIndicators)}
        </div>
        ${
            page.notes.length === 0
                ? nothing
                : html`<ul class="round-end-result__notes">
                      ${page.notes.map((note) => html`<li>${note}</li>`)}
                  </ul>`
        }
    </div>`;
}

/** The panel's foot: the scores, and the viewer's controls beside them when it has any. */
function ScoreFoot(
    rows: readonly ResultScoreRow[],
    controls: TemplateResult | undefined,
): TemplateResult {
    return html`<div class="round-end-result__foot">${ScoreGrid(rows)}${controls ?? nothing}</div>`;
}

function ScoreGrid(rows: readonly ResultScoreRow[]): TemplateResult {
    return html`<ol class="round-end-result__scores">
        ${rows.map(
            (row) => html`<li class="round-end-result__score">
                <span class="round-end-result__score-who">
                    <span class="round-end-result__score-wind"
                        >${row.wind.slice(0, 1)}<span class="round-end-result__score-wind-rest"
                            >${row.wind.slice(1)}</span
                        ></span
                    >
                    ${PlayerName(row.name, "round-end-result__score-name")}
                </span>
                ${row.tag === null ? nothing : html`<span class="round-end-result__score-tag">${row.tag}</span>`}
                <span class="round-end-result__delta ${deltaModifier(row.delta)}">${formatDelta(row.delta)}</span>
                <span class="round-end-result__score-after">${formatPoints(row.after)}</span>
            </li>`,
        )}
    </ol>`;
}

/** Says, on a result read against a table out of step, which of its parts may be wrong and which are the server's. */
function UncertainNote({ uncertain }: RoundEndDisplayState): TemplateResult | typeof nothing {
    return uncertain
        ? html`<span class="round-end-result__uncertain" role="note"
              >This page lost step with the server: the dora and dealer shown may be wrong. The hand and the
              scores are the server's.</span
          >`
        : nothing;
}

function WinPage(props: RoundEndDisplayProps, page: WinPageDisplay): TemplateResult {
    const { display } = props;
    return html`<div class="round-end-result round-end-result--win">
        <div class="round-end-result__head">
            <span class="round-end-result__kind">${page.title}</span>
            <span class="round-end-result__title">
                ${page.winnerName}
                <span class="round-end-result__wind">${page.winnerWind}</span>
            </span>
            ${page.fromName === null ? nothing : html`<span class="round-end-result__from">from ${page.fromName}</span>`}
            ${PagerControls(props)}
            ${UncertainNote(display)}
        </div>
        ${WinHand(page)}
        ${YakuList(page)}
        ${WinValue(page)}
        ${ScoreFoot(display.scores, props.controls)}
    </div>`;
}

function DrawPage(props: RoundEndDisplayProps, page: DrawPageDisplay): TemplateResult {
    const { controls, display } = props;
    return html`<div class="round-end-result round-end-result--draw">
        <div class="round-end-result__head">
            <span class="round-end-result__kind">Draw</span>
            <span class="round-end-result__title">${page.title}</span>
            ${page.subtitle === null ? nothing : html`<span class="round-end-result__from">${page.subtitle}</span>`}
            ${UncertainNote(display)}
        </div>
        ${
            page.tenpaiHands.length === 0
                ? nothing
                : html`<ul class="round-end-result__tenpai">
                      ${page.tenpaiHands.map((tenpai) => TenpaiHand(tenpai.name, tenpai.hand))}
                  </ul>`
        }
        ${ScoreFoot(display.scores, controls)}
    </div>`;
}

/**
 * One page of a round's result, as `roundEndDisplay` maps it: a winner's hand, value and payments, or the draw with
 * its tenpai hands. Given `onPage`, a result of several pages (a double ron's) pages between them.
 */
function RoundEndDisplay(props: RoundEndDisplayProps): TemplateResult {
    const { body } = props.display;
    return body.kind === "draw" ? DrawPage(props, body) : WinPage(props, body);
}

export { RoundEndDisplay };
