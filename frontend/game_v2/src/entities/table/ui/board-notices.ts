import { type TemplateResult, html, nothing } from "lit-html";
import { repeat } from "lit-html/directives/repeat.js";

import { type Notice } from "@/entities/table/model/notice";
import { HAND_TILE_FOCUS_KEY } from "@/entities/tile";
import { focusKeys } from "@/shared/lib";
import { focusOnFirstRender, keepTabInside } from "@/shared/ui";

import { DECISION_ACTION_FOCUS_KEY, PANEL_CONTROL_FOCUS_KEY, focusBackOnClose } from "./focus";
import { clampNotices } from "./notice-clamp";

/**
 * A notice as the board draws it (`Notice`), with a button when it offers a way out. One the board may open whole
 * (`onShowAll`, with the `id` its "Show all" is found by again) clamps to whole lines where its place is too short for it.
 */
export interface BoardNotice extends Notice {
    readonly action?: { readonly label: string; readonly onClick: () => void };
    readonly id?: string;
    readonly onShowAll?: () => void;
}

function noticeAction(notice: BoardNotice): TemplateResult | typeof nothing {
    const { action } = notice;
    if (action === undefined) {
        return nothing;
    }
    return html`<button type="button" class="board-notice__action" @click=${action.onClick}>${action.label}</button>`;
}

/** The focus key every "Show all" holds. */
const SHOW_ALL_FOCUS_KEY = "show-all";

/** The focus key of the "Show all" of the notice `id` names. */
function showAllKey(id: string | undefined): string | null {
    return id === undefined ? null : `${SHOW_ALL_FOCUS_KEY}:${id}`;
}

/**
 * "Show all", shown only while the notice is clamped; the whole notice is its tap target. Its name, which the clamp
 * writes, is the notice's words (`data-label`) and how many notices left out after it it opens too.
 */
function ShowAll(notice: BoardNotice): TemplateResult | typeof nothing {
    const { onShowAll } = notice;
    if (onShowAll === undefined) {
        return nothing;
    }
    return html`<button
        type="button"
        class="board-notice__more"
        data-label=${notice.text}
        data-focus-key=${focusKeys(showAllKey(notice.id), SHOW_ALL_FOCUS_KEY) ?? nothing}
        @click=${onShowAll}
    >
        Show all
    </button>`;
}

function noticeKey(notice: BoardNotice): string {
    return notice.id ?? notice.text;
}

/**
 * The notices' place in the table's left field, outside every river's capacity, so a notice never covers a tile, a
 * badge or a control: the notices, ongoing conditions first, each clamped to whole lines with "Show all" where the
 * stack is taller than the place, and under them what the board's page shows there too (a replay's position). They
 * are read out by `NoticeAnnouncements`, never from here, so a clamp is never announced.
 */
export function BoardNotices(
    notices: readonly BoardNotice[],
    after: TemplateResult | typeof nothing = nothing,
): TemplateResult {
    return html`<div class="board-notices" data-board-notices ${clampNotices()}>
        <div class="board-notices__list">${repeat(
            notices,
            noticeKey,
            (notice) =>
                html`<div class="board-notice board-notice--${notice.tone}" data-notice=${notice.id ?? nothing}>
                    <span class="board-notice__body">${notice.text}${noticeAction(notice)}</span>${ShowAll(notice)}
                </div>`,
        )}</div>
        ${after}
    </div>`;
}

/**
 * The notices as one polite live region, outside anything a panel makes inert, that reads only what it gains: not
 * atomic and relevant to additions alone, one line per notice keyed by its words, so a new notice is read alone, once,
 * and a redraw, a notice leaving or its clamp never.
 */
export function NoticeAnnouncements(notices: readonly BoardNotice[]): TemplateResult {
    return html`<div
        class="board-announce board-announce--notices"
        aria-live="polite"
        aria-atomic="false"
        aria-relevant="additions"
    >${repeat(
        notices,
        (notice) => notice.text,
        (notice) => html`<p>${notice.text}</p>`,
    )}</div>`;
}

/**
 * Where the focus goes once the sheet closes: the "Show all" that opened it while a player can reach it, else another,
 * else the panel the sheet gave way to, the decision's open controls or the hand's tiles, else the board itself: each by
 * the focus key its controls hold.
 */
function focusTargets(openerId: string): readonly string[] {
    return [
        `${SHOW_ALL_FOCUS_KEY}:${openerId}`,
        SHOW_ALL_FOCUS_KEY,
        PANEL_CONTROL_FOCUS_KEY,
        DECISION_ACTION_FOCUS_KEY,
        HAND_TILE_FOCUS_KEY,
    ];
}

/** A notice whole in the sheet, in its tone, with its way out. */
function SheetNotice(notice: BoardNotice): TemplateResult {
    const { action } = notice;
    return html`<li class="notice-sheet__notice notice-sheet__notice--${notice.tone}">
        <p class="notice-sheet__text">${notice.text}</p>
        ${
            action === undefined
                ? nothing
                : html`<button type="button" class="secondary notice-sheet__action" @click=${action.onClick}>
                      ${action.label}
                  </button>`
        }
    </li>`;
}

export interface NoticeSheetProps {
    readonly notices: readonly BoardNotice[];
    readonly openerId: string;
    readonly note: TemplateResult;
    readonly onClose: () => void;
}

/**
 * The notices opened whole, from the "Show all" of the one `openerId` names, in a sheet over the board as a panel is
 * (the board inert beneath it, which the board's caller sets): every notice of the stack in its order, each with its
 * way out, so one left out of a short place is read too; what the page says goes on meanwhile (`note`); and Close,
 * which takes the focus. Tab stays inside it, and Escape closes it alone. However it closes, the focus goes back to
 * the board (`focusTargets`), never to the page's body.
 */
export function NoticeSheet({
    notices,
    note,
    onClose,
    openerId,
}: NoticeSheetProps): TemplateResult {
    function onKeydown(event: KeyboardEvent): void {
        if (event.key === "Tab") {
            keepTabInside(event);
            return;
        }
        if (event.key === "Escape") {
            event.preventDefault();
            onClose();
        }
    }
    const title = notices.length === 1 ? "Notice" : "Notices";
    return html`<section
        class="notice-sheet"
        role="dialog"
        aria-modal="true"
        aria-label=${title}
        tabindex="-1"
        ${focusBackOnClose(focusTargets(openerId))}
        @keydown=${onKeydown}
    >
        <h2 class="notice-sheet__title">${title}</h2>
        <ul class="notice-sheet__list">${notices.map(SheetNotice)}</ul>
        ${note}
        <div class="notice-sheet__actions">
            <button
                type="button"
                class="notice-sheet__close"
                ${focusOnFirstRender()}
                @click=${onClose}
            >
                Close
            </button>
        </div>
    </section>`;
}
