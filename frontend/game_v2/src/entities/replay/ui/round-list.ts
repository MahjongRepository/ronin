import { type TemplateResult, html, nothing } from "lit-html";

import {
    type ReplayIncompleteness,
    type ReplayRoundRow,
} from "@/entities/replay/lib/replay-display";
import { type ReplayCursor } from "@/entities/replay/model/replay-cursor";
import { t } from "@/shared/i18n";

import { REPLAY_ROUND_LIST_ID } from "./replay-controls";

/** The list's way to the replay's last stop (its last result and the game's end, or where the recording ends). */
export interface RoundListEnd {
    readonly cursor: ReplayCursor;
    readonly current: boolean;
    readonly summary: string;
}

export interface RoundListProps {
    readonly rows: readonly ReplayRoundRow[];
    readonly end: RoundListEnd | null;
    readonly incomplete: ReplayIncompleteness | null;
    readonly onSelect: (start: ReplayCursor) => void;
    readonly onClose: () => void;
}

export const ROUND_LIST_ROW_CLASS = "round-list__row";

/** The focus key the current round's row renders, so the page focuses it as the list opens. */
export const CURRENT_ROUND_FOCUS_KEY = "current-round";

/** What the round list renders, so a page leaves its keys and wheel to it and knows a click inside it. */
export const ROUND_LIST_SELECTOR = "[data-round-list]";

/** The focus target `key` moves to among the rows, from the focused one; null for a key the list does not take. */
function rowAfterKey(rows: readonly HTMLElement[], from: number, key: string): HTMLElement | null {
    switch (key) {
        case "ArrowDown": {
            return rows[Math.min(from + 1, rows.length - 1)] ?? null;
        }
        case "ArrowUp": {
            return rows[Math.max(from - 1, 0)] ?? null;
        }
        case "Home": {
            return rows[0] ?? null;
        }
        case "End": {
            return rows.at(-1) ?? null;
        }
        default: {
            return null;
        }
    }
}

/**
 * The round list's keys stay its own: the arrows, Home and End move between its rounds, Escape closes it, and none of
 * them reaches the page's own keys.
 */
function onListKeydown(event: KeyboardEvent, onClose: () => void): void {
    const action = listKeyAction(event);
    if (action === null) {
        return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (action === "close") {
        onClose();
    } else {
        action.focus();
    }
}

/** What a key does in the list: close it, focus a row, or nothing the list takes (null). */
function listKeyAction(event: KeyboardEvent): "close" | HTMLElement | null {
    if (event.key === "Escape") {
        return "close";
    }
    const list = event.currentTarget;
    if (!(list instanceof HTMLElement)) {
        return null;
    }
    const rows = [...list.querySelectorAll<HTMLElement>(`.${ROUND_LIST_ROW_CLASS}`)];
    return rowAfterKey(
        rows,
        rows.findIndex((row) => row.matches(":focus")),
        event.key,
    );
}

function EndRow(
    end: RoundListEnd | null,
    onSelect: (cursor: ReplayCursor) => void,
): TemplateResult | typeof nothing {
    if (end === null) {
        return nothing;
    }
    return html`<div class="round-list__foot">
        <button
            type="button"
            class="${ROUND_LIST_ROW_CLASS} round-list__row--end"
            aria-current=${end.current ? "step" : nothing}
            @click=${() => onSelect(end.cursor)}
        >
            <span class="round-list__name">${t("replay.jump.last")}</span>
            <span class="round-list__summary">${end.summary}</span>
        </button>
    </div>`;
}

/**
 * Every round of the replay with its result in a line, the current one marked; choosing one opens its deal. Its foot,
 * in view however far the rounds scroll, goes to the replay's last stop, the touch way to the end. A replay that is not
 * the whole game says why at its head.
 */
export function RoundList(props: RoundListProps): TemplateResult {
    return html`<section
        class="round-list"
        data-round-list
        id=${REPLAY_ROUND_LIST_ID}
        aria-label=${t("replay.rounds.title")}
        @keydown=${(event: KeyboardEvent) => onListKeydown(event, props.onClose)}
    >
        <header class="round-list__head">
            <h2 class="round-list__title">${t("replay.rounds.title")}</h2>
            <button type="button" class="round-list__close" aria-label=${t("replay.rounds.close")} @click=${props.onClose}>
                ×
            </button>
        </header>
        ${
            props.incomplete === null
                ? nothing
                : html`<p class="round-list__incomplete">
                      <strong>${t("replay.rounds.incomplete_label", { label: props.incomplete.label })}</strong> ${props.incomplete.detail}
                  </p>`
        }
        <ol class="round-list__rows">
            ${props.rows.map(
                (row) => html`<li>
                    <button
                        type="button"
                        class=${ROUND_LIST_ROW_CLASS}
                        aria-current=${row.current ? "true" : nothing}
                        data-focus-key=${row.current ? CURRENT_ROUND_FOCUS_KEY : nothing}
                        @click=${() => props.onSelect(row.start)}
                    >
                        <span class="round-list__name">${row.name}</span>
                        <span class="round-list__summary">${row.summary}</span>
                    </button>
                </li>`,
            )}
        </ol>
        ${EndRow(props.end, props.onSelect)}
    </section>`;
}
