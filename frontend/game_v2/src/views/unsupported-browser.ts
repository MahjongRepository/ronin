import { type TemplateResult, html } from "lit-html";

import { t } from "@/shared/i18n";

export function unsupportedBrowserTemplate(lobbyUrl: string): TemplateResult {
    return html`<div class="browser-notice" role="alert">
        <h1 class="browser-notice__title">${t("common.unsupported_browser_title")}</h1>
        <p class="browser-notice__detail">${t("common.unsupported_browser")}</p>
        <a href=${lobbyUrl} role="button">${t("common.lobby")}</a>
    </div>`;
}
