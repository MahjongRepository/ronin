import { type TemplateResult, html, nothing } from "lit-html";

import { type ApiResult, apiGet, apiPost, isRecord } from "@/api";
import { t, tParts } from "@/i18n";

interface ApiTokenStatus {
    readonly hasAccount: boolean;
    readonly hasToken: boolean;
    readonly header: string;
}

interface ApiTokenState {
    failed: boolean;
    issuedToken: string | null;
    issuing: boolean;
    status: ApiTokenStatus | null;
}

interface ApiTokenContext {
    readonly isDisposed: () => boolean;
    readonly render: () => void;
}

const API_TOKEN_PATH = "/api/lobby/api-token";

function createApiTokenState(): ApiTokenState {
    return { failed: false, issuedToken: null, issuing: false, status: null };
}

function parseApiTokenStatus(data: unknown): ApiTokenStatus | null {
    if (!isRecord(data)) {
        return null;
    }
    const { has_account: hasAccount, has_token: hasToken, header } = data;
    if (typeof hasAccount !== "boolean" || typeof hasToken !== "boolean") {
        return null;
    }
    if (typeof header !== "string" || header === "") {
        return null;
    }
    return { hasAccount, hasToken, header };
}

function parseIssuedToken(data: unknown): string | null {
    return isRecord(data) && typeof data.token === "string" && data.token !== ""
        ? data.token
        : null;
}

async function loadApiTokenStatus(state: ApiTokenState, context: ApiTokenContext): Promise<void> {
    const result = await apiGet(API_TOKEN_PATH);
    if (context.isDisposed()) {
        return;
    }
    const status = result.ok ? parseApiTokenStatus(result.data) : null;
    if (status === null) {
        console.error("API token status not loaded", result.ok ? "invalid answer" : result.error);
        return;
    }
    state.status = status;
    context.render();
}

async function issueApiToken(state: ApiTokenState, context: ApiTokenContext): Promise<void> {
    if (state.issuing || state.status === null) {
        return;
    }
    state.issuing = true;
    state.failed = false;
    context.render();
    const result = await apiPost(API_TOKEN_PATH, {});
    if (!context.isDisposed()) {
        showIssuedToken(state, result);
        context.render();
    }
}

function showIssuedToken(state: ApiTokenState, result: ApiResult): void {
    state.issuing = false;
    const token = result.ok ? parseIssuedToken(result.data) : null;
    if (token === null || state.status === null) {
        console.error("API token not issued", result.ok ? "invalid answer" : result.error);
        state.failed = true;
        return;
    }
    state.issuedToken = token;
    state.status = { ...state.status, hasToken: true };
}

export interface ApiTokenSection {
    readonly available: () => boolean;
    readonly dispose: () => void;
    readonly template: () => TemplateResult | typeof nothing;
}

export function startApiTokenSection(render: () => void): ApiTokenSection {
    const state = createApiTokenState();
    let disposed = false;
    const context = { isDisposed: () => disposed, render };
    void loadApiTokenStatus(state, context);
    return {
        available: () => state.status?.hasAccount === true,
        dispose: () => {
            disposed = true;
        },
        template: () =>
            apiTokenTemplate(state, () => {
                void issueApiToken(state, context);
            }),
    };
}

function tokenStatusTemplate(state: ApiTokenState, hasToken: boolean): TemplateResult {
    if (state.issuedToken !== null) {
        return html`<div class="lobby-alert warning" role="status">
                <p>${t("settings.api_token.shown_once")}</p>
            </div>
            <label for="api-token"
                >${t("settings.api_token.token_label")}
                <input
                    type="text"
                    id="api-token"
                    .value=${state.issuedToken}
                    readonly
                    autocomplete="off"
                    spellcheck="false"
                />
            </label>`;
    }
    return html`<p>
        ${t(hasToken ? "settings.api_token.status_active" : "settings.api_token.status_none")}
    </p>`;
}

function apiTokenTemplate(
    state: ApiTokenState,
    issue: () => void,
): TemplateResult | typeof nothing {
    const { status } = state;
    if (status === null || !status.hasAccount) {
        return nothing;
    }
    function submit(event: SubmitEvent): void {
        event.preventDefault();
        issue();
    }
    const header = html`<code>${status.header}</code>`;
    return html`<div class="settings-api-token">
        <p class="lobby-muted">${tParts("settings.api_token.intro", { header })}</p>
        ${tokenStatusTemplate(state, status.hasToken)}
        ${
            state.failed
                ? html`<div class="lobby-alert" role="alert">
                      <p>${t("settings.api_token.failed")}</p>
                  </div>`
                : nothing
        }
        <form @submit=${submit}>
            ${
                status.hasToken
                    ? html`<p><small class="lobby-muted">${t("settings.api_token.rotate_note")}</small></p>
                          <button type="submit" class="outline" ?disabled=${state.issuing}>
                              ${t("settings.api_token.rotate")}
                          </button>`
                    : html`<button type="submit" ?disabled=${state.issuing}>
                          ${t("settings.api_token.generate")}
                      </button>`
            }
        </form>
    </div>`;
}
