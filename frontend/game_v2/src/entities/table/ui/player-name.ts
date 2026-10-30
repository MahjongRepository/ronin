import { type TemplateResult, html, nothing } from "lit-html";

import { nameParts } from "@/entities/table/lib/name-parts";

/** A player's name that a narrow column shortens in the middle, its end kept (`nameParts`); its title is the whole name. */
export function PlayerName(name: string, className: string): TemplateResult {
    const { head, tail } = nameParts(name);
    return html`<span class="player-name ${className}" title=${name}
        ><span class="player-name__head">${head}</span>${
            tail === "" ? nothing : html`<span class="player-name__tail">${tail}</span>`
        }</span
    >`;
}
