import { type TemplateResult, html } from "lit-html";

// 100-point stick: rounded rectangle with a 2×4 grid of small dots
function HonbaStickIcon(): TemplateResult {
    return html`
        <svg class="board-center__stick-icon" viewBox="0 0 10 24" aria-hidden="true">
            <rect x="1" y="0" width="8" height="24" rx="1.5" fill="#b0aaa2" />
            <circle cx="3.5" cy="4.5" r="1" fill="#2a2a2a" />
            <circle cx="6.5" cy="4.5" r="1" fill="#2a2a2a" />
            <circle cx="3.5" cy="9.5" r="1" fill="#2a2a2a" />
            <circle cx="6.5" cy="9.5" r="1" fill="#2a2a2a" />
            <circle cx="3.5" cy="14.5" r="1" fill="#2a2a2a" />
            <circle cx="6.5" cy="14.5" r="1" fill="#2a2a2a" />
            <circle cx="3.5" cy="19.5" r="1" fill="#2a2a2a" />
            <circle cx="6.5" cy="19.5" r="1" fill="#2a2a2a" />
        </svg>
    `;
}

export { HonbaStickIcon };
