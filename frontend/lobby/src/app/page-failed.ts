import { type TemplateResult, html } from "lit-html";

import { t } from "@/i18n";

export function pageFailedView(): TemplateResult {
    return html`<div class="lobby-alert" role="alert"><p>${t("common.page_failed")}</p></div>`;
}
