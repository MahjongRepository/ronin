import { type TemplateResult, html } from "lit-html";

/** A 1000-point stick: a rounded bar with one large centre dot, standing upright or lying across like a stick on a table. */
function RiichiStickIcon(lie: "upright" | "across" = "upright"): TemplateResult {
    if (lie === "across") {
        return html`
            <svg class="board-stick-icon" viewBox="0 0 32 6" aria-hidden="true">
                <rect class="board-stick-icon__body" x="0.5" y="0.5" width="31" height="5" rx="1.2" />
                <circle cx="16" cy="3" r="1.7" class="board-stick-icon__dot" />
            </svg>
        `;
    }
    return html`
        <svg class="board-stick-icon" viewBox="0 0 10 24" aria-hidden="true">
            <rect class="board-stick-icon__body" x="1" y="0.5" width="8" height="23" rx="1.5" />
            <circle cx="5" cy="12" r="2.5" class="board-stick-icon__dot" />
        </svg>
    `;
}

export { RiichiStickIcon };
