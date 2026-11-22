import { type TemplateResult, html } from "lit-html";

import { t } from "@/i18n";

export type ListLoadingShape = "rows" | "compact-rows" | "cards";

function rowTemplate(): TemplateResult {
    return html`<div class="list-loading-row">
        <span class="list-loading-bar list-loading-bar--lead"></span>
        <span class="list-loading-bar list-loading-bar--body"></span>
        <span class="list-loading-bar list-loading-bar--tail"></span>
    </div>`;
}

function cardTemplate(): TemplateResult {
    return html`<div class="list-loading-card">
        <span class="list-loading-bar list-loading-bar--lead"></span>
        ${[1, 2, 3, 4].map(() => html`<span class="list-loading-bar list-loading-bar--body"></span>`)}
        <span class="list-loading-bar list-loading-bar--tail"></span>
    </div>`;
}

export function listLoadingTemplate(shape: ListLoadingShape, count: number): TemplateResult {
    const items = Array.from({ length: count }, () =>
        shape === "cards" ? cardTemplate() : rowTemplate(),
    );
    return html`<div class="list-loading list-loading--${shape}" role="status">
        <span class="lobby-visually-hidden">${t("common.loading")}</span>
        <div class="list-loading-items" aria-hidden="true">${items}</div>
    </div>`;
}
