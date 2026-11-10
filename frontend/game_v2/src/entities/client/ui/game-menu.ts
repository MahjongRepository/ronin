import { type TemplateResult, html, nothing, svg } from "lit-html";

import { type CogAlert, type RoundTripDisplay } from "@/entities/client/model/round-trip";
import { SETTINGS_FOCUS_KEY } from "@/entities/client/model/settings-menu";
import { type SessionStatusDisplay } from "@/entities/session";
import { pageTileLabels } from "@/entities/tile";
import {
    LOCALES,
    type Locale,
    type MessageKey,
    WIND_LETTERS,
    WIND_SCRIPT_LANGS,
    type WindScript,
    pageLocale,
    pageWindScript,
    t,
    windScriptsOf,
} from "@/shared/i18n";
import { focusByKey } from "@/shared/lib";

interface GameMenuProps {
    /** The session's status, which a live game shows; null on a page without one (a replay). */
    readonly status: SessionStatusDisplay | null;
    /** The socket's round trip, shown beside the status; null while unmeasured or not connected. */
    readonly roundTrip?: RoundTripDisplay | null;
    /** The cog's mark, which the mapper chose; none on a page without a session (a replay). */
    readonly alert?: CogAlert | null;
    readonly open: boolean;
    /** Whether a full-page backdrop catches a click outside the open menu; a live board's `playInput` handles it instead. */
    readonly backdrop: boolean;
    readonly soundOn: boolean;
    readonly animationsOn: boolean;
    readonly onToggleOpen: () => void;
    readonly onClose: () => void;
    readonly onToggleSound: () => void;
    readonly onToggleAnimations: () => void;
    readonly onLanguage: (locale: Locale) => void;
    readonly onWinds: (script: WindScript) => void;
    readonly onTileLabels: (on: boolean) => void;
    /** The keyboard and mouse settings: the right-click switch and the controls' help it opens over the board. */
    readonly input?: {
        readonly rightClick: boolean;
        readonly onToggle: () => void;
        readonly keyHints: boolean;
        readonly onToggleKeyHints: () => void;
        readonly onShowControls: () => void;
    };
    /** Whether Auto win carries into the next round; a live game's alone. */
    readonly keepAutoWin?: { readonly on: boolean; readonly onToggle: () => void };
    /** The way back to the lobby: a live game's leave, asking first when `asks`, or a replay's link. */
    readonly leave?:
        | { readonly kind: "leave"; readonly asks: boolean; readonly onLeave: () => void }
        | { readonly kind: "link"; readonly href: string };
    /** What the page adds before the settings (the debug log). */
    readonly extra?: TemplateResult;
}

const LANGUAGE_NAMES: Readonly<Record<Locale, string>> = {
    en: "English",
    ja: "日本語",
    ru: "Русский",
};

const WIND_SCRIPT_NAMES: Readonly<Record<WindScript, MessageKey>> = {
    cyrillic: "game.settings.winds.cyrillic",
    kanji: "game.settings.winds.kanji",
    latin: "game.settings.winds.latin",
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

/** A door with an arrow out of it: leaving. */
function LeaveIcon(): TemplateResult {
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
        <path d="M6.5 2.5h-3.5v11h3.5" />
        <path d="M7 8h6.5M11 5.5l2.5 2.5-2.5 2.5" />
    </svg>`;
}

/**
 * The connection as the menu's row, a line of text like the other rows' values: the round trip once measured, its dot
 * and figure amber while slow, else the status's label with a dot in its tone.
 */
function ConnectionRow(
    status: SessionStatusDisplay,
    roundTrip: RoundTripDisplay | null,
): TemplateResult {
    const value =
        roundTrip === null
            ? html`<span class="game-menu__status-dot status-${status.tone}" aria-hidden="true"></span
                  >${status.label}`
            : html`<span class="game-menu__status-dot ${roundTrip.slow ? "status-slow" : "status-connected"}" aria-hidden="true"></span
                  ><span class=${roundTrip.slow ? "game-menu__round-trip game-menu__round-trip--slow" : "game-menu__round-trip"}
                      >${t("game.status.round_trip", { ms: Math.round(roundTrip.ms) })}</span
                  >`;
    return html`<div class="game-menu__item game-menu__status-row">
        <span class="game-menu__item-name">${t("game.settings.connection")}</span>
        <span class="game-menu__item-value game-menu__status">${value}</span>
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

/** The wind letters' script, from those the page's language offers, each option written in its own letters. */
function WindsRow(onWinds: (script: WindScript) => void): TemplateResult {
    const current = pageWindScript();
    return html`<div class="game-menu__item game-menu__language game-menu__winds" role="group" aria-label=${t("game.settings.winds")}>
        <span class="game-menu__item-name" aria-hidden="true">${t("game.settings.winds")}</span>
        <span class="game-menu__languages">${windScriptsOf(pageLocale()).map(
            (script) => html`<button
                type="button"
                class="secondary game-menu__language-option game-menu__winds-option"
                lang=${WIND_SCRIPT_LANGS[script]}
                data-script=${script}
                aria-label=${t(WIND_SCRIPT_NAMES[script])}
                aria-current=${script === current ? "true" : nothing}
                @click=${() => onWinds(script)}
            >${WIND_LETTERS[script].join("")}</button>`,
        )}</span>
    </div>`;
}

function SettingsPanel(props: GameMenuProps): TemplateResult {
    const {
        animationsOn,
        backdrop,
        onClose,
        onLanguage,
        onToggleAnimations,
        onTileLabels,
        onToggleSound,
        onWinds,
        soundOn,
        status,
    } = props;
    return html`${backdrop ? html`<div class="game-menu__backdrop" aria-hidden="true" @click=${onClose}></div>` : nothing}
        <div class="game-menu__panel" role="group" aria-label=${t("game.settings.title")}>
            <button
                type="button"
                class="secondary game-menu__item game-menu__sound"
                role="switch"
                aria-checked=${soundOn ? "true" : "false"}
                @click=${onToggleSound}
            >
                ${SoundIcon(soundOn)}<span class="game-menu__item-name">${t("game.settings.sound")}</span
                >${SwitchValue(soundOn)}
            </button>
            <button
                type="button"
                class="secondary game-menu__item game-menu__animations"
                role="switch"
                aria-checked=${animationsOn ? "true" : "false"}
                @click=${onToggleAnimations}
            >
                <span class="game-menu__item-name">${t("game.settings.animations")}</span
                >${SwitchValue(animationsOn)}
            </button>
            ${TileLabelsRow(onTileLabels)}
            ${props.keepAutoWin === undefined ? nothing : KeepAutoWinRow(props.keepAutoWin)}
            ${props.input === undefined ? nothing : InputSettings(props.input)}
            ${LanguageRow(onLanguage)}
            ${WindsRow(onWinds)}
            ${props.input === undefined ? nothing : ControlsRow(props.input.onShowControls)}
            ${status === null ? nothing : ConnectionRow(status, props.roundTrip ?? null)}
            ${props.leave === undefined ? nothing : LeaveRow(props.leave)}
        </div>`;
}

function LeaveRow(leave: NonNullable<GameMenuProps["leave"]>): TemplateResult {
    if (leave.kind === "link") {
        return html`<a
            href=${leave.href}
            role="button"
            class="secondary game-menu__item game-menu__leave"
        >${LeaveIcon()}<span class="game-menu__item-name">${t("common.back_to_lobby")}</span></a>`;
    }
    return html`<button
        type="button"
        class="secondary game-menu__item game-menu__leave"
        aria-haspopup=${leave.asks ? "dialog" : nothing}
        @click=${leave.onLeave}
    >${LeaveIcon()}<span class="game-menu__item-name">${t("game.settings.leave")}</span></button>`;
}

function onOff(on: boolean): string {
    return t(on ? "game.settings.on" : "game.settings.off");
}

/**
 * A switch's state at its row's end, reserving the other state's width (`data-reserve`), so a toggle never resizes the
 * menu when its row is the widest.
 */
function SwitchValue(on: boolean): TemplateResult {
    return html`<span class="game-menu__item-value game-menu__switch-value" data-reserve=${onOff(!on)}
        ><span>${onOff(on)}</span></span
    >`;
}

/** The tiles' corner labels: a suit tile's rank, a wind's letter in the chosen script. */
function TileLabelsRow(onTileLabels: (on: boolean) => void): TemplateResult {
    const on = pageTileLabels() !== null;
    return html`<button
        type="button"
        class="secondary game-menu__item game-menu__tile-labels"
        role="switch"
        aria-checked=${String(on)}
        @click=${() => onTileLabels(!on)}
    ><span class="game-menu__item-name">${t("game.settings.tile_labels")}</span
        >${SwitchValue(on)}</button>`;
}

function KeepAutoWinRow(keep: NonNullable<GameMenuProps["keepAutoWin"]>): TemplateResult {
    return html`<button
        type="button"
        class="secondary game-menu__item game-menu__keep-auto-win"
        role="switch"
        aria-checked=${String(keep.on)}
        @click=${keep.onToggle}
    ><span class="game-menu__item-name">${t("game.settings.keep_auto_win")}</span
        >${SwitchValue(keep.on)}</button>`;
}

function InputSettings(input: NonNullable<GameMenuProps["input"]>): TemplateResult {
    return html`<button
        type="button"
            class="secondary game-menu__item game-menu__right-click"
        role="switch"
        aria-checked=${String(input.rightClick)}
        @click=${input.onToggle}
    ><span class="game-menu__item-name">${t("game.settings.right_click")}</span
        >${SwitchValue(input.rightClick)}</button>
        <button
            type="button"
            class="secondary game-menu__item game-menu__key-hints"
            role="switch"
            aria-checked=${String(input.keyHints)}
            @click=${input.onToggleKeyHints}
        ><span class="game-menu__item-name">${t("game.settings.key_hints")}</span
            >${SwitchValue(input.keyHints)}</button>`;
}

/** The row that opens the controls' help panel. */
function ControlsRow(onShowControls: () => void): TemplateResult {
    return html`<button
        type="button"
        class="secondary game-menu__item game-menu__controls"
        aria-haspopup="dialog"
        @click=${onShowControls}
    ><span class="game-menu__item-name">${t("game.help.title")}</span
        ><span class="game-menu__item-value" aria-hidden="true">›</span></button>`;
}

/**
 * The page's own controls in the board's corner: a cog that opens the settings (the sound, and a live game's session
 * status), marked while the status has a word to say (a drop, an end) or the round trip is slow, and the status read
 * out as it changes whether the menu is open or not. Escape closes the open menu and focuses the cog back.
 */
function GameMenu(props: GameMenuProps): TemplateResult {
    const { extra, onClose, onToggleOpen, open, status } = props;
    const alert = props.alert ?? null;
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
            aria-label=${alert === null ? t("game.settings.title") : t("game.settings.title_with_status", { status: alert.word })}
            aria-expanded=${open ? "true" : "false"}
            data-focus-key=${SETTINGS_FOCUS_KEY}
            @click=${onToggleOpen}
        >
            ${CogIcon()}${
                alert === null
                    ? nothing
                    : html`<span class="game-menu__alert status-${alert.tone}"></span>`
            }
        </button>
        ${open ? SettingsPanel(props) : nothing}
    </nav>`;
}

export { GameMenu };
export type { GameMenuProps };
