import { type SetBoardAppearance } from "@ronin/shared/board-appearance";
import {
    AnimationsRow,
    BoardAppearanceRows,
    InputRows,
    type InputRowsProps,
    KeepAutoWinRow,
    LanguageRow,
    SoundRow,
    type SwitchRowProps,
    WindsRow,
} from "@ronin/shared/settings-rows";
import { type TemplateResult, html, nothing } from "lit-html";

import { type CogAlert, type RoundTripDisplay } from "@/entities/client/model/round-trip";
import { SETTINGS_FOCUS_KEY } from "@/entities/client/model/settings-menu";
import { type SessionStatusDisplay } from "@/entities/session";
import { type Locale, type WindScript, t } from "@/shared/i18n";
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
    readonly onBoardAppearance: SetBoardAppearance;
    /** The keyboard and mouse settings: the right-click switch and the controls' help it opens over the board. */
    readonly input?: InputRowsProps & { readonly onShowControls: () => void };
    /** Whether Auto win carries into the next round; a live game's alone. */
    readonly keepAutoWin?: SwitchRowProps;
    /** The way back to the lobby: a live game's leave, asking first when `asks`, or a replay's link. */
    readonly leave?:
        | { readonly kind: "leave"; readonly asks: boolean; readonly onLeave: () => void }
        | { readonly kind: "link"; readonly href: string };
    /** What the page adds before the settings (the debug log). */
    readonly extra?: TemplateResult;
}

const MENU_BLOCK = "game-menu";

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

function SettingsPanel(props: GameMenuProps): TemplateResult {
    const {
        animationsOn,
        backdrop,
        onClose,
        onLanguage,
        onToggleAnimations,
        onBoardAppearance,
        onToggleSound,
        onWinds,
        soundOn,
        status,
    } = props;
    return html`${backdrop ? html`<div class="game-menu__backdrop" aria-hidden="true" @click=${onClose}></div>` : nothing}
        <div class="game-menu__panel" role="group" aria-label=${t("game.settings.title")}>
            ${SoundRow(MENU_BLOCK, { on: soundOn, onToggle: onToggleSound })}
            ${AnimationsRow(MENU_BLOCK, { on: animationsOn, onToggle: onToggleAnimations })}
            ${BoardAppearanceRows(MENU_BLOCK, onBoardAppearance)}
            ${props.keepAutoWin === undefined ? nothing : KeepAutoWinRow(MENU_BLOCK, props.keepAutoWin)}
            ${props.input === undefined ? nothing : InputRows(MENU_BLOCK, props.input)}
            ${LanguageRow(MENU_BLOCK, onLanguage)}
            ${WindsRow(MENU_BLOCK, onWinds)}
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
