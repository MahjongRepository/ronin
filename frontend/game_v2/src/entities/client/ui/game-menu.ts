import { type TemplateResult, html, nothing, svg } from "lit-html";

import { type SessionStatusDisplay } from "@/entities/session";
import { focusByKey } from "@/shared/lib";

interface GameMenuProps {
    /** The session's status, which a live game shows; null on a page without one (a replay). */
    readonly status: SessionStatusDisplay | null;
    readonly open: boolean;
    readonly soundOn: boolean;
    readonly onToggleOpen: () => void;
    readonly onClose: () => void;
    readonly onToggleSound: () => void;
    /** What the page adds before the settings (the debug log). */
    readonly extra?: TemplateResult;
}

const SETTINGS_FOCUS_KEY = "settings";

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
        <span class="game-menu__item-name">Status</span>
        <span class="connection-status game-menu__status status-${status.tone}">${status.label}</span>
    </div>`;
}

/**
 * The menu's items: the sound switch, then the session's status where the page has one. A backdrop under them closes
 * the menu on a tap anywhere else, which takes no other action.
 */
function SettingsPanel(props: GameMenuProps): TemplateResult {
    const { onClose, onToggleSound, soundOn, status } = props;
    return html`<div class="game-menu__backdrop" aria-hidden="true" @click=${onClose}></div>
        <div class="game-menu__panel" role="group" aria-label="Settings">
            <button
                type="button"
                class="secondary game-menu__item game-menu__sound"
                role="switch"
                aria-checked=${soundOn ? "true" : "false"}
                @click=${onToggleSound}
            >
                ${SoundIcon(soundOn)}<span class="game-menu__item-name">Sound</span
                ><span class="game-menu__item-value">${soundOn ? "On" : "Off"}</span>
            </button>
            ${status === null ? nothing : StatusRow(status)}
        </div>`;
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
    return html`<nav class="game-menu" aria-label="Game" @keydown=${onKeydown}>
        ${extra ?? nothing}
        ${
            status === null
                ? nothing
                : html`<span class="game-menu__status-label" role="status">${status.label}</span>`
        }
        <button
            type="button"
            class="secondary game-menu__toggle"
            title="Settings"
            aria-label=${word === "" ? "Settings" : `Settings, ${word}`}
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
