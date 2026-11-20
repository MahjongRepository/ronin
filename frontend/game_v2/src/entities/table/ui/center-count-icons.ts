import { type TemplateResult, html, svg } from "lit-html";

const LYING_STICK_BODY = svg`<rect class="board-stick-icon__body" x="0.5" y="0.5" width="19" height="6" rx="1.4" />`;

function LyingHonbaStickIcon(): TemplateResult {
    return html`
        <svg class="board-stick-icon board-stick-icon--lying" viewBox="0 0 20 7" aria-hidden="true">
            ${LYING_STICK_BODY}
            <circle cx="3.3" cy="2.4" r="1" class="board-stick-icon__honba" />
            <circle cx="5.7" cy="2.4" r="1" class="board-stick-icon__honba" />
            <circle cx="3.3" cy="4.6" r="1" class="board-stick-icon__honba" />
            <circle cx="5.7" cy="4.6" r="1" class="board-stick-icon__honba" />
            <circle cx="14.3" cy="2.4" r="1" class="board-stick-icon__honba" />
            <circle cx="16.7" cy="2.4" r="1" class="board-stick-icon__honba" />
            <circle cx="14.3" cy="4.6" r="1" class="board-stick-icon__honba" />
            <circle cx="16.7" cy="4.6" r="1" class="board-stick-icon__honba" />
        </svg>
    `;
}

function LyingRiichiStickIcon(): TemplateResult {
    return html`
        <svg class="board-stick-icon board-stick-icon--lying" viewBox="0 0 20 7" aria-hidden="true">
            ${LYING_STICK_BODY}
            <circle cx="10" cy="3.5" r="2" class="board-stick-icon__dot" />
        </svg>
    `;
}

function WallTileIcon(): TemplateResult {
    return html`
        <svg class="board-wall-icon" viewBox="0 0 8 11" aria-hidden="true">
            <rect class="board-wall-icon__back" x="0.5" y="0.5" width="7" height="10" rx="1.2" />
            <path class="board-wall-icon__face" d="M0.5 3V1.7A1.2 1.2 0 0 1 1.7 0.5H6.3A1.2 1.2 0 0 1 7.5 1.7V3Z" />
        </svg>
    `;
}

export { LyingHonbaStickIcon, LyingRiichiStickIcon, WallTileIcon };
