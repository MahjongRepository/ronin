import { type TemplateResult, html } from "lit-html";

import { formatNumber } from "@/shared/i18n";

export function withSecondsFigure(
    text: string,
    seconds: number,
    figureClass: string,
): TemplateResult {
    const figure = formatNumber(seconds);
    const at = text.indexOf(figure);
    if (at === -1) {
        return html`${text}`;
    }
    return html`${text.slice(0, at)}<span class=${figureClass}>${figure}</span>${text.slice(at + figure.length)}`;
}
