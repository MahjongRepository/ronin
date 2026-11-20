import { type TemplateResult, html } from "lit-html";

function WallTileIcon(): TemplateResult {
    return html`
        <svg class="board-wall-icon" viewBox="0 0 8 11" aria-hidden="true">
            <rect class="board-wall-icon__back" x="0.5" y="0.5" width="7" height="10" rx="1.2" />
            <path class="board-wall-icon__face" d="M0.5 3V1.7A1.2 1.2 0 0 1 1.7 0.5H6.3A1.2 1.2 0 0 1 7.5 1.7V3Z" />
        </svg>
    `;
}

export { WallTileIcon };
