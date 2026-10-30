import { type TemplateResult, html, nothing } from "lit-html";

import {
    type LedgerCell,
    type LedgerRow,
    type StandingsDisplay,
    type StandingsSeat,
} from "@/entities/table/lib/standings-display";

import { RiichiStickIcon } from "./riichi-stick-icon";

/** A way on from the standings: a link to another page, or a control of the view's own. */
export type StandingsAction =
    | {
          readonly kind: "link";
          readonly label: string;
          readonly href: string;
          readonly primary?: boolean;
      }
    | {
          readonly kind: "button";
          readonly label: string;
          readonly onClick: () => void;
          readonly primary?: boolean;
      };

export interface StandingsPanelProps {
    readonly display: StandingsDisplay;
    /** Its ways on, in order; the one marked primary is the panel's primary action. */
    readonly actions: readonly StandingsAction[];
    /** Shows a round's result: given it, each ledger row is a button (the replay's), else the rows only read. */
    readonly onRound?: (round: number) => void;
}

function columnClass(seat: StandingsSeat, base: string): string {
    return seat.viewer ? `${base} standings__col--viewer` : base;
}

function cellClass(cell: LedgerCell, seat: StandingsSeat): string {
    const classes = [columnClass(seat, "standings__cell"), `standings__cell--${cell.tone}`];
    if (cell.mark === "win") {
        classes.push("standings__cell--win");
    }
    return classes.join(" ");
}

function cellTitle(cell: LedgerCell): string | typeof nothing {
    const marks = [
        cell.dealer ? "dealer" : "",
        cell.riichi ? "riichi" : "",
        cell.mark === "win" ? "won" : "",
        cell.mark === "deal_in" ? "dealt in" : "",
    ].filter((mark) => mark !== "");
    return marks.length === 0 ? nothing : marks.join(", ");
}

type MarkKind = "dealer" | "win" | "deal-in";

function Mark(kind: MarkKind): TemplateResult {
    return html`<span class="standings__mark standings__mark--${kind}" aria-hidden="true"></span>`;
}

function RiichiMark(): TemplateResult {
    return html`<span class="standings__riichi" aria-hidden="true">${RiichiStickIcon()}</span>`;
}

function cellMarks(cell: LedgerCell): TemplateResult[] {
    const marks: TemplateResult[] = [];
    if (cell.dealer) {
        marks.push(Mark("dealer"));
    }
    if (cell.riichi) {
        marks.push(RiichiMark());
    }
    if (cell.mark === "win") {
        marks.push(Mark("win"));
    } else if (cell.mark === "deal_in") {
        marks.push(Mark("deal-in"));
    }
    return marks;
}

function StandingsCell(cell: LedgerCell, seat: StandingsSeat): TemplateResult {
    return html`<td class=${cellClass(cell, seat)} title=${cellTitle(cell)}>
        ${cellMarks(cell)}<span class="standings__delta">${cell.text}</span>
    </td>`;
}

/** What the ledger's marks mean, on the panel itself, since a touch screen shows no tooltip. */
function StandingsLegend(): TemplateResult {
    return html`<p class="standings__legend">
        <span class="standings__legend-item">${Mark("dealer")}Dealer</span>
        <span class="standings__legend-item">${RiichiMark()}Riichi</span>
        <span class="standings__legend-item">${Mark("win")}Won</span>
        <span class="standings__legend-item">${Mark("deal-in")}Dealt in</span>
    </p>`;
}

function StandingsRoundLabel(row: LedgerRow): TemplateResult {
    return html`<span class="standings__round-name"
            >${row.name}${row.honba > 0 ? html`<span class="standings__honba">${row.honba} honba</span>` : nothing}</span
        ><span class="standings__outcome">${row.outcome}</span>`;
}

function roundTitle(row: LedgerRow): string {
    const honba = row.honba > 0 ? `, ${row.honba} honba` : "";
    return `${row.name}${honba}: ${row.summary}`;
}

function StandingsRoundRow(
    row: LedgerRow,
    seats: readonly StandingsSeat[],
    onRound: StandingsPanelProps["onRound"],
): TemplateResult {
    const label =
        onRound === undefined
            ? html`<span class="standings__round" title=${roundTitle(row)}>${StandingsRoundLabel(row)}</span>`
            : html`<button
                  type="button"
                  class="standings__round standings__round--jump"
                  aria-label="${roundTitle(row)}. Show its result"
                  @click=${() => onRound(row.round)}
              >
                  ${StandingsRoundLabel(row)}
              </button>`;
    return html`<tr>
        <th scope="row" class="standings__label">${label}</th>
        ${row.cells.map((cell, index) => StandingsCell(cell, seats[index]))}
    </tr>`;
}

interface FootRowProps {
    readonly label: TemplateResult | string;
    readonly cells: readonly string[];
    readonly seats: readonly StandingsSeat[];
    readonly modifier: string;
}

function StandingsFootRow({ cells, label, modifier, seats }: FootRowProps): TemplateResult {
    return html`<tr class="standings__foot-row standings__foot-row--${modifier}">
        <th scope="row" class="standings__label">${label}</th>
        ${cells.map((text, index) => html`<td class=${columnClass(seats[index], "standings__cell")}>${text}</td>`)}
    </tr>`;
}

function StandingsFoot({ leftover, seats }: StandingsDisplay): TemplateResult {
    const leftoverRow =
        leftover === null
            ? nothing
            : StandingsFootRow({
                  cells: leftover.cells,
                  label: html`<span title="Leftover riichi sticks, paid to the winner"
                      >Leftover<span class="standings__note">×${leftover.sticks}</span></span
                  >`,
                  modifier: "leftover",
                  seats,
              });
    return html`<tfoot>
        ${leftoverRow}
        ${StandingsFootRow({
            cells: seats.map((seat) => seat.score),
            label: "Final score",
            modifier: "score",
            seats,
        })}
        <tr class="standings__foot-row standings__foot-row--result">
            <th scope="row" class="standings__label">Result<span class="standings__note">uma/oka</span></th>
            ${seats.map(
                (seat) =>
                    html`<td class="${columnClass(seat, "standings__cell")} standings__cell--${seat.resultTone}">
                        ${seat.result}
                    </td>`,
            )}
        </tr>
    </tfoot>`;
}

function StandingsActionView(action: StandingsAction): TemplateResult {
    const classes = `standings__action${action.primary === true ? "" : " secondary"}`;
    if (action.kind === "link") {
        return html`<a class=${classes} role="button" href=${action.href}>${action.label}</a>`;
    }
    return html`<button type="button" class=${classes} @click=${action.onClick}>${action.label}</button>`;
}

/**
 * The final standings: a column per seat in placement order (placement, name, the viewer's highlighted), a row per
 * finished round with each seat's change in it (its riichi, the dealer, the winners and who paid a ron marked), then
 * the leftover riichi sticks, the final scores and the uma/oka results; its head says what the marks mean. The
 * rounds scroll between the names and the totals, which stay in view. Given `onRound`, a row shows that round's
 * result.
 */
export function StandingsPanel({ actions, display, onRound }: StandingsPanelProps): TemplateResult {
    const { ledger, seats } = display;
    return html`<section class="standings" aria-label="Final standings">
        <header class="standings__head">
            <h2 class="standings__title">Final standings</h2>
            ${StandingsLegend()}
            <div class="standings__actions">${actions.map(StandingsActionView)}</div>
        </header>
        <div class="standings__sheet" tabindex="0" role="region" aria-label="Scores by round">
            <table class="standings__table">
                <thead>
                    <tr>
                        <th scope="col" class="standings__label">
                            <span class="standings__hint">${onRound === undefined ? "Round" : "Tap a round"}</span>
                        </th>
                        ${seats.map(
                            (
                                seat,
                            ) => html`<th scope="col" class=${columnClass(seat, "standings__seat")}>
                                <span class="standings__placement">${seat.placement}</span>
                                <span class="standings__name" title=${seat.name}>${seat.name}</span>
                            </th>`,
                        )}
                    </tr>
                </thead>
                <tbody>
                    ${ledger.map((row) => StandingsRoundRow(row, seats, onRound))}
                </tbody>
                ${StandingsFoot(display)}
            </table>
        </div>
    </section>`;
}
