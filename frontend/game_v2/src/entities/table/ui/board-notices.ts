import { type TemplateResult, html, nothing } from "lit-html";

export type BoardNoticeTone = "info" | "success" | "warning" | "error";

/**
 * A line of news over the table: a connection's state, a refused move, a message the client could not read, tile
 * faces that did not load; with a button when it offers a way out.
 */
export interface BoardNotice {
    readonly text: string;
    readonly tone: BoardNoticeTone;
    readonly action?: { readonly label: string; readonly onClick: () => void };
}

function noticeAction(notice: BoardNotice): TemplateResult | typeof nothing {
    const { action } = notice;
    if (action === undefined) {
        return nothing;
    }
    return html`<button type="button" class="board-notice__action" @click=${action.onClick}>${action.label}</button>`;
}

/**
 * The notices over the table, stacked at its top edge, inside the table's own area so they never cover the local
 * hand or the decision's corner. The stack is one polite live region, so each notice is read as it appears.
 */
export function BoardNotices(notices: readonly BoardNotice[]): TemplateResult {
    return html`<div class="board-notices" role="status" aria-live="polite">
        ${notices.map(
            (notice) =>
                html`<p class="board-notice board-notice--${notice.tone}">${notice.text}${noticeAction(notice)}</p>`,
        )}
    </div>`;
}
