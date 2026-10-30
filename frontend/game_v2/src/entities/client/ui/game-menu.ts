import { type TemplateResult, html, nothing } from "lit-html";

import { type LeaveControls, type PlayCommand } from "@/entities/client/model/play-display";
import { type SessionStatusDisplay } from "@/entities/session";
import { CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";

/** The word the corner shows beside its dot: none while connected, a short one otherwise, the notices saying more. */
const STATUS_WORDS: Readonly<Record<ConnectionStatus, string>> = {
    [CONNECTION_STATUS.CONNECTED]: "",
    [CONNECTION_STATUS.CONNECTING]: "Connecting",
    [CONNECTION_STATUS.DISCONNECTED]: "Offline",
    [CONNECTION_STATUS.ERROR]: "Error",
};

interface GameMenuProps {
    readonly status: SessionStatusDisplay;
    readonly leave: LeaveControls;
    readonly onCommand: (command: PlayCommand) => void;
    /** What the page adds before the status (the debug log). */
    readonly extra?: TemplateResult;
}

/** A door with an arrow out of it: leave the table for the lobby. */
function LeaveIcon(): TemplateResult {
    return html`<svg
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M6.5 2.5h-3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3M10 5l3 3-3 3M13 8H6" />
    </svg>`;
}

/**
 * The page's own controls in the board's corner: the session's status as a dot and a short word (its whole label
 * read out and in its title) and the way back, which asks first while leaving would hand the seat to an AI.
 */
function GameMenu({ extra, leave, onCommand, status }: GameMenuProps): TemplateResult {
    const word = STATUS_WORDS[status.tone];
    return html`<nav class="game-menu" aria-label="Game">
        ${extra ?? nothing}
        <span class="connection-status game-menu__status status-${status.tone}" role="status" title=${status.label}
            ><span class="game-menu__status-label">${status.label}</span>${
                word === ""
                    ? nothing
                    : html`<span class="game-menu__status-word" aria-hidden="true">${word}</span>`
            }</span
        >
        <button
            class="secondary game-menu__leave"
            title="Back to the lobby"
            aria-haspopup=${leave.command.kind === "ask_leave" ? "dialog" : nothing}
            @click=${() => onCommand(leave.command)}
        >
            ${LeaveIcon()}<span class="game-menu__leave-label">Lobby</span>
        </button>
    </nav>`;
}

export { GameMenu };
export type { GameMenuProps };
