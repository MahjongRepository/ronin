import { type TemplateResult, html } from "lit-html";

import { t } from "@/i18n";

export function seatNamesTemplate(seats: readonly (string | null)[]): TemplateResult {
    return html`<span class="seat-names">
        ${seats.map((name) =>
            name === null
                ? html`<span class="seat-name seat-name--free">${t("seat.free")}</span>`
                : html`<span class="seat-name" title=${name}>${name}</span>`,
        )}
    </span>`;
}
