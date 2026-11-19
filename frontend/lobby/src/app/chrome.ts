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

function withoutTrailingSlash(path: string): string {
    return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

function currentPage(path: string, href: string): "page" | typeof nothing {
    return withoutTrailingSlash(path) === href ? "page" : nothing;
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

function adminItem(path: string): TemplateResult {
    return html`<li>
        <a
            href=${MONITORING_PATH}
            class="lobby-nav-link"
            aria-current=${currentPage(path, MONITORING_PATH)}
            >${t("nav.admin")}</a
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

function personIcon(): TemplateResult {
    return html`<svg
        class="lobby-account-icon"
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <circle cx="8" cy="5.5" r="2.75" />
        <path d="M2.75 14c0-2.9 2.35-4.75 5.25-4.75s5.25 1.85 5.25 4.75" />
    </svg>`;
}

function chevronIcon(): TemplateResult {
    return html`<svg
        class="lobby-account-chevron"
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M4 6l4 4 4-4" />
    </svg>`;
}

function logoutIcon(): TemplateResult {
    return html`<svg
        class="lobby-account-item-icon"
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M6.5 2.5h-3.5v11h3.5" />
        <path d="M7 8h6.5M11 5.5l2.5 2.5-2.5 2.5" />
    </svg>`;
}

interface AccountMenu {
    readonly open: boolean;
    readonly close: () => void;
    readonly closeAndFocusToggle: () => void;
    readonly toggle: () => void;
}

const ACCOUNT_PANEL_ID = "lobby-account-panel";

function closeOnEscape(menu: AccountMenu): (event: KeyboardEvent) => void {
    return (event) => {
        if (event.key !== "Escape" || !menu.open) {
            return;
        }
        event.preventDefault();
        menu.closeAndFocusToggle();
    };
}

function closeOnItemChoice(menu: AccountMenu): (event: MouseEvent) => void {
    return (event) => {
        if (event.target instanceof Element && event.target.closest("a, button")) {
            menu.close();
        }
    };
}

function accountPanel(user: SessionUser, path: string, menu: AccountMenu): TemplateResult {
    return html`<div
        id=${ACCOUNT_PANEL_ID}
        class="lobby-account-panel"
        ?hidden=${!menu.open}
        @click=${closeOnItemChoice(menu)}
    >
        <p class="lobby-account-name">${user.username}</p>
        <a
            href=${SETTINGS_PATH}
            class="lobby-account-item"
            aria-current=${currentPage(path, SETTINGS_PATH)}
            >${cogIcon()}<span>${t("nav.settings")}</span></a
        >
        <hr class="lobby-account-divider" />
        <form method="POST" action="/logout" @submit=${postCurrentCsrfToken}>
            <input type="hidden" name="csrf_token" value=${readCsrfToken()} />
            <button type="submit" class="lobby-account-item">
                ${logoutIcon()}<span>${t("nav.log_out")}</span>
            </button>
        </form>
    </div>`;
}

function accountItems(user: SessionUser, path: string, menu: AccountMenu): TemplateResult {
    return html`<li class="lobby-account-menu" @keydown=${closeOnEscape(menu)}>
        <button
            type="button"
            class="lobby-account-toggle"
            aria-expanded=${menu.open ? "true" : "false"}
            aria-controls=${ACCOUNT_PANEL_ID}
            aria-label=${t("nav.account_menu", { username: user.username })}
            @click=${menu.toggle}
        >
            ${personIcon()}<span class="lobby-username" title=${user.username}>${user.username}</span
            >${chevronIcon()}
        </button>
        ${accountPanel(user, path, menu)}
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

function rightItems(
    session: Session | undefined,
    url: URL,
    menu: AccountMenu,
): TemplateResult | typeof nothing {
    if (session === undefined) {
        return nothing;
    }
    return session.user ? accountItems(session.user, url.pathname, menu) : signInItems(url);
}

function navTemplate(session: Session | undefined, url: URL, menu: AccountMenu): TemplateResult {
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
            ${rightItems(session, url, menu)}
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
    let accountOpen = false;

    function setAccountOpen(open: boolean): void {
        accountOpen = open;
        drawChrome();
    }

    function accountMenu(): AccountMenu {
        return {
            close: () => setAccountOpen(false),
            closeAndFocusToggle: () => {
                setAccountOpen(false);
                mounts.nav.querySelector<HTMLButtonElement>(".lobby-account-toggle")?.focus();
            },
            open: accountOpen,
            toggle: () => setAccountOpen(!accountOpen),
        };
    }

    function closeOnOutsideClick(event: MouseEvent): void {
        const menu = mounts.nav.querySelector(".lobby-account-menu");
        if (accountOpen && !(event.target instanceof Node && menu?.contains(event.target))) {
            setAccountOpen(false);
        }
    }

    function renderChrome(): void {
        accountOpen = false;
        drawChrome();
    }

    function drawChrome(): void {
        const url = new URL(window.location.href);
        mounts.nav.setAttribute("aria-label", t("nav.aria_label"));
        render(navTemplate(session, url, accountMenu()), mounts.nav);
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

    document.addEventListener("click", closeOnOutsideClick);
    return {
        render: renderChrome,
        showSession(loaded) {
            session = loaded;
            renderChrome();
        },
        switchLanguage,
    };
}
