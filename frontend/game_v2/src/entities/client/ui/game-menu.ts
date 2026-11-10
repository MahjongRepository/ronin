import { type TemplateResult, html, nothing, svg } from "lit-html";

import { switchLetters } from "@/entities/client/model/play-display";
import { SETTINGS_FOCUS_KEY } from "@/entities/client/model/settings-menu";
import { type SessionStatusDisplay } from "@/entities/session";
import { LOCALES, type Locale, pageLocale, t } from "@/shared/i18n";
import { focusByKey } from "@/shared/lib";

interface GameMenuProps {
    /** The session's status, which a live game shows; null on a page without one (a replay). */
    readonly status: SessionStatusDisplay | null;
    readonly open: boolean;
    readonly soundOn: boolean;
    readonly animationsOn: boolean;
    readonly onToggleOpen: () => void;
    readonly onClose: () => void;
    readonly onToggleSound: () => void;
    readonly onToggleAnimations: () => void;
    readonly onLanguage: (locale: Locale) => void;
    readonly input?: { readonly rightClick: boolean; readonly onToggle: () => void };
    /** Whether Auto win carries into the next round; a live game's alone. */
    readonly keepAutoWin?: { readonly on: boolean; readonly onToggle: () => void };
    /** What the page adds before the settings (the debug log). */
    readonly extra?: TemplateResult;
}

const LANGUAGE_NAMES: Readonly<Record<Locale, string>> = {
    en: "English",
    ja: "日本語",
    ru: "Русский",
};

/** A cog: the settings. */
function CogIcon(): TemplateResult {
    return html`<svg viewBox="0 0 24 24" aria-hidden="true">
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

/** A speaker, sounding or struck through. */
function SoundIcon(on: boolean): TemplateResult {
    return html`<svg
        class="game-menu__icon"
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M2.5 6h2.5l3.5-3v10l-3.5-3h-2.5z" />
        ${
            on
                ? svg`<path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.5a6 6 0 0 1 0 9" />`
                : svg`<path d="M11 6l3.5 4M14.5 6l-3.5 4" />`
        }
    </svg>`;
}

/** The session's status as the menu's row: a dot and its whole label. */
function StatusRow(status: SessionStatusDisplay): TemplateResult {
    return html`<div class="game-menu__item game-menu__status-row">
        <span class="game-menu__item-name">${t("game.settings.status")}</span>
        <span class="connection-status game-menu__status status-${status.tone}">${status.label}</span>
    </div>`;
}

function LanguageRow(onLanguage: (locale: Locale) => void): TemplateResult {
    const current = pageLocale();
    return html`<div class="game-menu__item game-menu__language" role="group" aria-label=${t("game.settings.language")}>
        <span class="game-menu__item-name" aria-hidden="true">${t("game.settings.language")}</span>
        <span class="game-menu__languages">${LOCALES.map(
            (locale) => html`<button
                type="button"
                class="secondary game-menu__language-option"
                lang=${locale}
                aria-current=${locale === current ? "true" : nothing}
                @click=${() => onLanguage(locale)}
            >${LANGUAGE_NAMES[locale]}</button>`,
        )}</span>
    </div>`;
}

function SettingsPanel(props: GameMenuProps): TemplateResult {
    const {
        animationsOn,
        onClose,
        onLanguage,
        onToggleAnimations,
        onToggleSound,
        soundOn,
        status,
    } = props;
    return html`<div class="game-menu__backdrop" aria-hidden="true" @click=${onClose}></div>
        <div class="game-menu__panel" role="group" aria-label=${t("game.settings.title")}>
            <button
                type="button"
                class="secondary game-menu__item game-menu__sound"
                role="switch"
                aria-checked=${soundOn ? "true" : "false"}
                @click=${onToggleSound}
            >
                ${SoundIcon(soundOn)}<span class="game-menu__item-name">${t("game.settings.sound")}</span
                ><span class="game-menu__item-value">${onOff(soundOn)}</span>
            </button>
            <button
                type="button"
                class="secondary game-menu__item game-menu__animations"
                role="switch"
                aria-checked=${animationsOn ? "true" : "false"}
                @click=${onToggleAnimations}
            >
                <span class="game-menu__item-name">${t("game.settings.animations")}</span
                ><span class="game-menu__item-value">${onOff(animationsOn)}</span>
            </button>
            ${props.keepAutoWin === undefined ? nothing : KeepAutoWinRow(props.keepAutoWin)}
            ${LanguageRow(onLanguage)}
            ${props.input === undefined ? nothing : InputSettings(props.input)}
            ${status === null ? nothing : StatusRow(status)}
        </div>`;
}

function onOff(on: boolean): string {
    return t(on ? "game.settings.on" : "game.settings.off");
}

function KeepAutoWinRow(keep: NonNullable<GameMenuProps["keepAutoWin"]>): TemplateResult {
    return html`<button
        type="button"
        class="secondary game-menu__item game-menu__keep-auto-win"
        role="switch"
        aria-checked=${String(keep.on)}
        @click=${keep.onToggle}
    ><span class="game-menu__item-name">${t("game.settings.keep_auto_win")}</span
        ><span class="game-menu__item-value">${onOff(keep.on)}</span></button>`;
}

function InputSettings(input: NonNullable<GameMenuProps["input"]>): TemplateResult {
    return html`<button
        type="button"
            class="secondary game-menu__item game-menu__right-click"
        role="switch"
        aria-checked=${String(input.rightClick)}
        @click=${input.onToggle}
    ><span class="game-menu__item-name">${t("game.settings.right_click")}</span
        ><span class="game-menu__item-value">${onOff(input.rightClick)}</span></button>
        <details class="game-menu__controls">
            <summary>${t("game.help.title")}</summary>
            <p>${t("game.help.tiles")}</p>
            <p>${t("game.help.escape")}</p>
            <p>${t("game.help.decline", {
                pass: t("game.button.pass"),
                ron: t("game.call.ron"),
                tsumo: t("game.call.tsumo"),
            })}</p>
            <p>${t("game.help.results", {
                letters: switchLetters().join("/"),
                next: t("game.result.next"),
                ok: t("common.ok"),
            })}</p>
        </details>`;
}

/**
 * The page's own controls in the board's corner: a cog that opens the settings (the sound, and a live game's session
 * status), marked with the status's tone while the status has a word to say (a drop, an end), and the status read out
 * as it changes whether the menu is open or not. Escape closes the open menu and focuses the cog back.
 */
function GameMenu(props: GameMenuProps): TemplateResult {
    const { extra, onClose, onToggleOpen, open, status } = props;
    const word = status?.word ?? "";
    function onKeydown(event: KeyboardEvent): void {
        if (event.key !== "Escape" || !open || !(event.currentTarget instanceof HTMLElement)) {
            return;
        }
        event.preventDefault();
        const nav = event.currentTarget;
        onClose();
        focusByKey(nav, SETTINGS_FOCUS_KEY);
    }
    return html`<nav class="game-menu" aria-label=${t("game.menu.label")} @keydown=${onKeydown}>
        ${extra ?? nothing}
        ${
            status === null
                ? nothing
                : html`<span class="game-menu__status-label" role="status">${status.label}</span>`
        }
        <button
            type="button"
            class="secondary game-menu__toggle"
            title=${t("game.settings.title")}
            aria-label=${word === "" ? t("game.settings.title") : t("game.settings.title_with_status", { status: word })}
            aria-expanded=${open ? "true" : "false"}
            data-focus-key=${SETTINGS_FOCUS_KEY}
            @click=${onToggleOpen}
        >
            ${CogIcon()}${
                status === null || word === ""
                    ? nothing
                    : html`<span class="game-menu__alert status-${status.tone}"></span>`
            }
        </button>
        ${open ? SettingsPanel(props) : nothing}
    </nav>`;
}

export { GameMenu };
export type { GameMenuProps };
