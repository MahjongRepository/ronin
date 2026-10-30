import { type TemplateResult, html } from "lit-html";

// 100-point stick: rounded rectangle with a 2×4 grid of small dots
function HonbaStickIcon(): TemplateResult {
    return html`
        <svg class="board-stick-icon" viewBox="0 0 10 24" aria-hidden="true">
            <rect class="board-stick-icon__body" x="1" y="0.5" width="8" height="23" rx="1.5" />
            <circle cx="3.5" cy="4.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="6.5" cy="4.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="3.5" cy="9.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="6.5" cy="9.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="3.5" cy="14.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="6.5" cy="14.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="3.5" cy="19.5" r="1.4" class="board-stick-icon__honba" />
            <circle cx="6.5" cy="19.5" r="1.4" class="board-stick-icon__honba" />
        </svg>
    `;
}

export { HonbaStickIcon };
