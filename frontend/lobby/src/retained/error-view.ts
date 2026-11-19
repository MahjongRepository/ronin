import { type TemplateResult, html, nothing, render } from "lit-html";

import { type MessageKey, reportI18nError, t } from "@/i18n";

export interface ErrorPage {
    readonly actionHref: string;
    readonly code: string;
    readonly status: string;
}

interface ErrorText {
    readonly message: MessageKey;
    readonly title: MessageKey;
}

const LOBBY_PATH = "/";

const SERVER_FAILURE: ErrorText = { message: "error.server.message", title: "error.server.title" };

const ERROR_TEXT: ReadonlyMap<string, ErrorText> = new Map([
    ["not_found", { message: "error.not_found.message", title: "error.not_found.title" }],
    ["refused", { message: "error.refused.message", title: "error.refused.title" }],
    ["server", SERVER_FAILURE],
    [
        "session_expired",
        { message: "error.session_expired.message", title: "error.session_expired.title" },
    ],
]);

function metaContent(name: string): string {
    return document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)?.content ?? "";
}

export function readErrorPage(): ErrorPage {
    return {
        actionHref: metaContent("ronin-error-action") || LOBBY_PATH,
        code: metaContent("ronin-error-code"),
        status: metaContent("ronin-error-status"),
    };
}

function errorText(code: string): ErrorText {
    const text = ERROR_TEXT.get(code);
    if (text === undefined) {
        reportI18nError(`error.${code}`, "unknown error code");
        return SERVER_FAILURE;
    }
    return text;
}

function errorTemplate(page: ErrorPage, title: string, message: string): TemplateResult {
    const reloads = page.actionHref !== LOBBY_PATH;
    return html`<p class="lobby-error-code">${page.status}</p>
        <h1 id="error-title">${title}</h1>
        <p class="lobby-muted">${message}</p>
        <p class="lobby-button-row lobby-button-row--center lobby-error-actions">
            <a href=${page.actionHref} role="button"
                >${reloads ? t("error.reload_page") : t("common.back_to_lobby")}</a
            >
            ${
                reloads
                    ? html`<a href=${LOBBY_PATH} role="button" class="outline secondary"
                      >${t("common.back_to_lobby")}</a
                  >`
                    : nothing
            }
        </p>`;
}

export function renderErrorView(host: HTMLElement, page: ErrorPage): void {
    const text = errorText(page.code);
    const title = t(text.title);
    document.title = t("page.title.with_page", { page: title });
    render(errorTemplate(page, title, t(text.message)), host);
}
