import { type TemplateResult, html } from "lit-html";

// 1000-point stick: rounded rectangle with a single large center dot
function RiichiStickIcon(): TemplateResult {
    return html`
        <svg class="board-center__stick-icon" viewBox="0 0 10 24" aria-hidden="true">
            <rect x="1" y="0" width="8" height="24" rx="1.5" fill="#b0aaa2" />
            <circle cx="5" cy="12" r="2.5" fill="#d45454" />
        </svg>
    `;
}

export { RiichiStickIcon };
