import { type TemplateResult, html } from "lit-html";

// 1000-point stick: rounded rectangle with a single large center dot
function RiichiStickIcon(): TemplateResult {
    return html`
        <svg class="board-stick-icon" viewBox="0 0 10 24" aria-hidden="true">
            <rect class="board-stick-icon__body" x="1" y="0.5" width="8" height="23" rx="1.5" />
            <circle cx="5" cy="12" r="2.5" class="board-stick-icon__dot" />
        </svg>
    `;
}

export { RiichiStickIcon };
