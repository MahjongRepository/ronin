import { type TemplateResult, html } from "lit-html";

export type BoardNoticeTone = "info" | "success" | "warning" | "error";

/** A line of news over the table: a connection's state, a refused move, a message the client could not read. */
export interface BoardNotice {
    readonly text: string;
    readonly tone: BoardNoticeTone;
}

/**
 * The notices over the table, stacked at its top edge, inside the table's own area so they never cover the local
 * hand or the decision's corner. The stack is one polite live region, so each notice is read as it appears.
 */
export function BoardNotices(notices: readonly BoardNotice[]): TemplateResult {
    return html`<div class="board-notices" role="status" aria-live="polite">
        ${notices.map(
            (notice) =>
                html`<p class="board-notice board-notice--${notice.tone}">${notice.text}</p>`,
        )}
    </div>`;
}
