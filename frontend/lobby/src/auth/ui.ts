import { type TemplateResult, html, nothing, render } from "lit-html";

import {
    AUTH_FIELD,
    type AuthField,
    type AuthFields,
    type AuthState,
    errorField,
    nextQuery,
} from "@/auth/state";
import { t, tParts } from "@/i18n";

export interface AuthActions {
    readonly startGuest: () => void;
    readonly submit: (fields: AuthFields) => void;
}

const FORM_ERROR_ID = "form-error";

function readFields(event: SubmitEvent): AuthFields | null {
    const form = event.currentTarget;
    if (!(form instanceof HTMLFormElement)) {
        return null;
    }
    const data = new FormData(form);
    const confirmPassword = data.get(AUTH_FIELD.CONFIRM_PASSWORD);
    return {
        confirmPassword: typeof confirmPassword === "string" ? confirmPassword : null,
        password: String(data.get(AUTH_FIELD.PASSWORD) ?? ""),
        username: String(data.get(AUTH_FIELD.USERNAME) ?? ""),
    };
}

function onSubmit(actions: AuthActions): (event: SubmitEvent) => void {
    return (event) => {
        event.preventDefault();
        const fields = readFields(event);
        if (fields !== null) {
            actions.submit(fields);
        }
    };
}

function onGuest(actions: AuthActions): (event: SubmitEvent) => void {
    return (event) => {
        event.preventDefault();
        actions.startGuest();
    };
}

function describedBy(...ids: (string | null)[]): string | typeof nothing {
    const present = ids.filter((id) => id !== null);
    return present.length > 0 ? present.join(" ") : nothing;
}

function errorId(state: AuthState, field: AuthField): string | null {
    return errorField(state) === field ? FORM_ERROR_ID : null;
}

function invalid(state: AuthState, field: AuthField): "true" | typeof nothing {
    return state.error?.field === field ? "true" : nothing;
}

function autofocused(state: AuthState, field: AuthField): boolean {
    return (errorField(state) ?? AUTH_FIELD.USERNAME) === field;
}

function errorAlert(state: AuthState): TemplateResult | typeof nothing {
    if (state.error === null) {
        return nothing;
    }
    return html`<div class="lobby-alert" role="alert" id=${FORM_ERROR_ID}>
        <p>${t(state.error.key, state.error.params)}</p>
    </div>`;
}

function headingTemplate(title: string, subtitle: string): TemplateResult {
    return html`<hgroup>
        <h1>${title}</h1>
        <p>${subtitle}</p>
    </hgroup>`;
}

function legalNotice(): TemplateResult {
    return html`<p class="auth-legal">
        ${tParts("auth.legal.notice", {
            privacy: html`<a href="/privacy">${t("auth.legal.privacy_link")}</a>`,
            terms: html`<a href="/terms">${t("auth.legal.terms_link")}</a>`,
        })}
    </p>`;
}

function loginForm(state: AuthState, actions: AuthActions): TemplateResult {
    const { limits } = state;
    return html`<form @submit=${onSubmit(actions)}>
        <label for="username"
            >${t("auth.field.username")}
            <input
                type="text"
                id="username"
                name="username"
                .value=${state.username}
                required
                minlength=${limits?.usernameMinLength ?? nothing}
                maxlength=${limits?.usernameMaxLength ?? nothing}
                autocomplete="username"
                autocapitalize="none"
                spellcheck="false"
                aria-invalid=${invalid(state, AUTH_FIELD.USERNAME)}
                aria-describedby=${describedBy(errorId(state, AUTH_FIELD.USERNAME))}
                ?autofocus=${autofocused(state, AUTH_FIELD.USERNAME)}
        /></label>
        <label for="password"
            >${t("auth.field.password")}
            <input
                type="password"
                id="password"
                name="password"
                required
                autocomplete="current-password"
                aria-invalid=${invalid(state, AUTH_FIELD.PASSWORD)}
                aria-describedby=${describedBy(errorId(state, AUTH_FIELD.PASSWORD))}
                ?autofocus=${autofocused(state, AUTH_FIELD.PASSWORD)}
        /></label>
        <button type="submit">${t("auth.login.submit")}</button>
    </form>`;
}

function loginTemplate(state: AuthState, actions: AuthActions): TemplateResult {
    return html`<article class="auth-card">
        ${headingTemplate(t("auth.login.title"), t("auth.login.subtitle"))} ${errorAlert(state)}
        ${loginForm(state, actions)}
        <p class="auth-divider">${t("auth.login.or")}</p>
        <form @submit=${onGuest(actions)}>
            <button type="submit" class="outline" aria-describedby="guest-note"
                >${t("auth.login.guest")}</button
            >
            <p class="auth-note" id="guest-note">${t("auth.login.guest_note")}</p>
        </form>
        <p class="auth-link">
            <small
                >${tParts("auth.login.no_account", {
                    register: html`<a href="/register${nextQuery(state)}"
                        >${t("auth.login.register_link")}</a
                    >`,
                })}</small
            >
        </p>
        ${legalNotice()}
    </article>`;
}

function usernameHelp(state: AuthState): string | typeof nothing {
    const { limits } = state;
    return limits
        ? t("auth.register.username_help", {
              max: limits.usernameMaxLength,
              min: limits.usernameMinLength,
          })
        : nothing;
}

function passwordHelp(state: AuthState): string | typeof nothing {
    return state.limits
        ? t("auth.register.password_help", { count: state.limits.passwordMinLength })
        : nothing;
}

function newPasswordInput(
    state: AuthState,
    field: AuthField,
    helpId: string | null,
): TemplateResult {
    const { limits } = state;
    return html`<input
        type="password"
        id=${field}
        name=${field}
        required
        minlength=${limits?.passwordMinLength ?? nothing}
        maxlength=${limits?.passwordMaxLength ?? nothing}
        autocomplete="new-password"
        aria-invalid=${invalid(state, field)}
        aria-describedby=${describedBy(helpId, errorId(state, field))}
        ?autofocus=${autofocused(state, field)}
    />`;
}

function registerForm(state: AuthState, actions: AuthActions): TemplateResult {
    const { limits } = state;
    return html`<form @submit=${onSubmit(actions)}>
        <label for="username"
            >${t("auth.field.username")}
            <input
                type="text"
                id="username"
                name="username"
                .value=${state.username}
                required
                minlength=${limits?.usernameMinLength ?? nothing}
                maxlength=${limits?.usernameMaxLength ?? nothing}
                autocomplete="username"
                autocapitalize="none"
                spellcheck="false"
                aria-invalid=${invalid(state, AUTH_FIELD.USERNAME)}
                aria-describedby=${describedBy(
                    "username-help",
                    errorId(state, AUTH_FIELD.USERNAME),
                )}
                ?autofocus=${autofocused(state, AUTH_FIELD.USERNAME)}
            />
            <small id="username-help">${usernameHelp(state)}</small>
        </label>
        <label for="password"
            >${t("auth.field.password")} ${newPasswordInput(state, AUTH_FIELD.PASSWORD, "password-help")}
            <small id="password-help">${passwordHelp(state)}</small>
        </label>
        <label for="confirm_password"
            >${t("auth.field.confirm_password")}
            ${newPasswordInput(state, AUTH_FIELD.CONFIRM_PASSWORD, null)}
        </label>
        <button type="submit">${t("auth.register.submit")}</button>
    </form>`;
}

function registerTemplate(state: AuthState, actions: AuthActions): TemplateResult {
    return html`<article class="auth-card">
        ${headingTemplate(t("auth.register.title"), t("auth.register.subtitle"))}
        ${errorAlert(state)} ${registerForm(state, actions)}
        <p class="auth-link">
            <small
                >${tParts("auth.register.have_account", {
                    log_in: html`<a href="/login${nextQuery(state)}"
                        >${t("auth.register.log_in_link")}</a
                    >`,
                })}</small
            >
        </p>
        ${legalNotice()}
    </article>`;
}

export function renderAuth(host: HTMLElement, state: AuthState, actions: AuthActions): void {
    const titleKey = state.page === "login" ? "auth.login.title" : "auth.register.title";
    document.title = t("page.title.with_page", { page: t(titleKey) });
    const template =
        state.page === "login" ? loginTemplate(state, actions) : registerTemplate(state, actions);
    render(template, host);
}

export function clearPasswordsAndFocusErrorField(host: HTMLElement, state: AuthState): void {
    for (const input of host.querySelectorAll<HTMLInputElement>("input[type=password]")) {
        input.value = "";
    }
    const field = errorField(state);
    if (field !== null) {
        host.querySelector<HTMLInputElement>(`#${field}`)?.focus();
    }
}
