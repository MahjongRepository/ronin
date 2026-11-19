import { supportsBoardCss } from "@ronin/shared/browser-support";
import { LANGUAGE_NAMES, LOCALES, type Locale } from "@ronin/shared/locale";
import { switchLocale } from "@ronin/shared/locale-switch";
import { type TemplateResult, html, nothing, render } from "lit-html";

import { type PageMeta, readCsrfToken } from "@/app/page-meta";
import { type Session, type SessionUser } from "@/app/session";
import { pageLocale, t } from "@/i18n";

export interface ChromeMounts {
    readonly footer: HTMLElement;
    readonly nav: HTMLElement;
    readonly notice: HTMLElement | null;
}

export interface Chrome {
    readonly render: () => void;
    readonly showSession: (session: Session) => void;
    readonly switchLanguage: (locale: Locale) => void;
}

const MONITORING_PATH = "/admin/monitoring";
const SETTINGS_PATH = "/settings";

function currentPage(path: string, href: string): "page" | typeof nothing {
    return path === href ? "page" : nothing;
}

function nextQuery(url: URL): string {
    const next = url.searchParams.get("next");
    return next ? `?${new URLSearchParams({ next }).toString()}` : "";
}

function userLinks(user: SessionUser, path: string): TemplateResult {
    return html`<li>
            <a href="/history" class="lobby-nav-link" aria-current=${currentPage(path, "/history")}
                >${t("nav.history")}</a
            >
        </li>
        ${user.isAdmin ? adminItem(path) : nothing}`;
}

function adminIcon(): TemplateResult {
    return html`<svg
        class="lobby-nav-icon"
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M2.5 13.5h11" />
        <path d="M4.5 13.5v-4M8 13.5v-9M11.5 13.5v-6" />
    </svg>`;
}

function adminItem(path: string): TemplateResult {
    return html`<li>
        <a
            href=${MONITORING_PATH}
            class="lobby-nav-link lobby-admin-link"
            aria-label=${t("nav.admin")}
            title=${t("nav.admin")}
            aria-current=${currentPage(path, MONITORING_PATH)}
            >${adminIcon()}<span class="lobby-admin-label">${t("nav.admin")}</span></a
        >
    </li>`;
}

function postCurrentCsrfToken(event: SubmitEvent): void {
    const form = event.currentTarget;
    const input = form instanceof HTMLFormElement ? form.elements.namedItem("csrf_token") : null;
    if (input instanceof HTMLInputElement) {
        input.value = readCsrfToken();
    }
}

function cogIcon(): TemplateResult {
    return html`<svg class="lobby-settings-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle
            cx="12"
            cy="12"
            r="8.5"
            fill="none"
            stroke="currentColor"
            stroke-width="3.5"
            stroke-dasharray="3.338 3.338"
        />
        <circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2.5" />
    </svg>`;
}

function settingsItem(user: SessionUser, path: string): TemplateResult {
    return html`<li class="lobby-settings-item">
        <a
            href=${SETTINGS_PATH}
            class="lobby-nav-link lobby-settings-link"
            aria-label=${t("nav.settings")}
            title=${t("nav.settings")}
            aria-current=${currentPage(path, SETTINGS_PATH)}
            >${cogIcon()}<span class="lobby-username">${user.username}</span></a
        >
    </li>`;
}

function accountItems(user: SessionUser, path: string): TemplateResult {
    return html`${settingsItem(user, path)}
        <li>
            <form method="POST" action="/logout" @submit=${postCurrentCsrfToken}>
                <input type="hidden" name="csrf_token" value=${readCsrfToken()} />
                <button type="submit" class="lobby-logout">${t("nav.log_out")}</button>
            </form>
        </li>`;
}

function signInItems(url: URL): TemplateResult {
    const query = nextQuery(url);
    return html`<li>
            <a href="/login${query}" class="lobby-nav-link" aria-current=${currentPage(url.pathname, "/login")}
                >${t("nav.log_in")}</a
            >
        </li>
        <li>
            <a
                href="/register${query}"
                role="button"
                class="outline lobby-small-btn"
                aria-current=${currentPage(url.pathname, "/register")}
                >${t("nav.register")}</a
            >
        </li>`;
}

function rightItems(session: Session | undefined, url: URL): TemplateResult | typeof nothing {
    if (session === undefined) {
        return nothing;
    }
    return session.user ? accountItems(session.user, url.pathname) : signInItems(url);
}

function navTemplate(session: Session | undefined, url: URL): TemplateResult {
    const user = session?.user ?? null;
    return html`<ul>
            <li>
                <a href="/" class="lobby-brand"
                    ><span class="lobby-logo" aria-hidden="true"></span
                    ><span class="lobby-wordmark">Ronin <span class="lobby-beta">${t("nav.beta")}</span></span></a
                >
            </li>
            ${user ? userLinks(user, url.pathname) : nothing}
        </ul>
        <ul class=${user ? "lobby-account" : nothing}>
            ${rightItems(session, url)}
        </ul>`;
}

function versionTemplate(meta: PageMeta): TemplateResult | string {
    if (!meta.releaseUrl) {
        return `v${meta.appVersion}`;
    }
    return html`<a href=${meta.releaseUrl} target="_blank" rel="noopener">v${meta.appVersion}</a>`;
}

function devLinksTemplate(meta: PageMeta): TemplateResult | typeof nothing {
    if (!meta.devMode) {
        return nothing;
    }
    return html`<nav class="footer-dev-links" aria-label=${t("footer.dev_links_label")}>
        <a href="/storybook">${t("footer.lobby_storybook")}</a>
        <a href="/play/storybook">${t("footer.game_storybook")}</a>
    </nav>`;
}

function languageButtons(onLanguage: (locale: Locale) => void): TemplateResult[] {
    const current = pageLocale();
    return LOCALES.map(
        (locale) =>
            html`<button
                type="button"
                lang=${locale}
                aria-current=${locale === current ? "true" : nothing}
                @click=${() => onLanguage(locale)}
            >${LANGUAGE_NAMES[locale]}</button>`,
    );
}

function footerTemplate(
    meta: PageMeta,
    path: string,
    onLanguage: (locale: Locale) => void,
): TemplateResult {
    return html`<div class="footer-content">
        <small class="footer-meta"
            >&copy; ${meta.currentYear} Ronin &middot; ${versionTemplate(meta)} &middot;
            <a href="/terms" aria-current=${currentPage(path, "/terms")}>${t("footer.terms")}</a>
            &middot;
            <a href="/privacy" aria-current=${currentPage(path, "/privacy")}>${t("footer.privacy")}</a></small
        >
        <form class="footer-lang" aria-label=${t("footer.language_label")}>${languageButtons(onLanguage)}</form>
        ${devLinksTemplate(meta)}
    </div>`;
}

function renderNotice(notice: HTMLElement): void {
    notice.hidden = supportsBoardCss();
    render(html`<p>${t("common.unsupported_browser")}</p>`, notice);
}

export function startChrome(
    mounts: ChromeMounts,
    meta: PageMeta,
    onLanguageSwitched: () => void,
): Chrome {
    let session: Session | undefined = undefined;

    function renderChrome(): void {
        const url = new URL(window.location.href);
        mounts.nav.setAttribute("aria-label", t("nav.aria_label"));
        render(navTemplate(session, url), mounts.nav);
        render(footerTemplate(meta, url.pathname, switchLanguage), mounts.footer);
        if (mounts.notice) {
            renderNotice(mounts.notice);
        }
    }

    function switchLanguage(locale: Locale): void {
        if (locale === pageLocale()) {
            return;
        }
        switchLocale(locale);
        renderChrome();
        onLanguageSwitched();
    }

    return {
        render: renderChrome,
        showSession(loaded) {
            session = loaded;
            renderChrome();
        },
        switchLanguage,
    };
}
