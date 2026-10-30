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
 * The notices' place in the table's left field, outside every river's capacity, so a notice never covers a tile, a
 * badge or a control: the notices, one polite live region so each is read as it appears, and under them what the
 * board's page shows there too (a replay's position and narration).
 */
export function BoardNotices(
    notices: readonly BoardNotice[],
    after: TemplateResult | typeof nothing = nothing,
): TemplateResult {
    return html`<div class="board-notices">
        <div class="board-notices__list" role="status" aria-live="polite">${notices.map(
            (notice) =>
                html`<p class="board-notice board-notice--${notice.tone}">${notice.text}${noticeAction(notice)}</p>`,
        )}</div>
        ${after}
    </div>`;
}
