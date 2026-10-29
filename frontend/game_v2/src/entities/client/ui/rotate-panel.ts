import { type TemplateResult, html } from "lit-html";

import { type DecisionCountdown, decisionCountdown } from "@/entities/client/model/countdown";
import { type GameClientState } from "@/entities/client/model/types";
import {
    type SessionStatusDisplay,
    describePlayerSessionStatus,
    describeSessionStatus,
} from "@/entities/session";
import { CONNECTION_STATUS } from "@/shared/protocol";

const NO_SESSION_STATUS: SessionStatusDisplay = {
    label: "No session",
    tone: CONNECTION_STATUS.ERROR,
};

const NOT_CONNECTED_STATUS: SessionStatusDisplay = {
    label: "Not connected",
    tone: CONNECTION_STATUS.ERROR,
};

/** The seconds left at which the countdown is announced to a screen reader, the largest first. */
const ANNOUNCED_SECONDS = [10, 5] as const;

export interface RotatePanelProps {
    readonly status: SessionStatusDisplay;
    readonly countdown: DecisionCountdown | null;
    readonly onLeave: () => void;
}

/** The session's status line for a live client's state, in the machine's own terms, for the debug view. */
export function describeClientStatus(state: GameClientState): SessionStatusDisplay {
    return state.session === null ? NO_SESSION_STATUS : describeSessionStatus(state.session);
}

export function rotatePanelProps(state: GameClientState, onLeave: () => void): RotatePanelProps {
    const status =
        state.session === null ? NOT_CONNECTED_STATUS : describePlayerSessionStatus(state.session);
    return { countdown: decisionCountdown(state), onLeave, status };
}

function moveName(move: DecisionCountdown["move"]): string {
    return move === "turn" ? "It is your turn" : "You can call the last discard";
}

/**
 * What the polite live region says: it changes only when the countdown crosses a threshold or expires, so a screen
 * reader is not read the seconds every second.
 */
function countdownAnnouncement(countdown: DecisionCountdown | null): string {
    if (countdown?.kind === "expired") {
        return "Time is up";
    }
    if (countdown?.kind !== "running") {
        return "";
    }
    const crossed = ANNOUNCED_SECONDS.findLast((seconds) => countdown.secondsLeft <= seconds);
    return crossed === undefined ? "" : `${crossed} seconds or less left`;
}

function countdownTemplate(countdown: DecisionCountdown): TemplateResult {
    if (countdown.kind === "expired") {
        return html`<div class="rotate-panel__decision rotate-panel__decision--expired">
            <p>${moveName(countdown.move)}, and its time is up: the server makes the move.</p>
        </div>`;
    }
    const left =
        countdown.kind === "running"
            ? html`<p class="rotate-panel__countdown" aria-live="off">
                  <span class="rotate-panel__seconds">${countdown.secondsLeft}</span> s left
              </p>`
            : "";
    return html`<div class="rotate-panel__decision">
        <p>${moveName(countdown.move)}. Play and its timer go on while the phone is upright.</p>
        ${left}
    </div>`;
}

function rotateIcon(): TemplateResult {
    return html`<svg class="rotate-panel__icon" viewBox="0 0 64 64" aria-hidden="true">
        <rect x="22" y="8" width="20" height="36" rx="3" />
        <path d="M14 50 a20 20 0 0 0 36 0" />
        <path d="M44 46 l6 4 l-1 -7" />
    </svg>`;
}

/**
 * The full-screen notice the live game shows instead of the table on an upright phone: it asks to turn the phone,
 * shows the session's status for a player, and while a decision awaits the viewer, that the game and its countdown
 * go on. Only the status line and the countdown's thresholds are live regions.
 */
export function RotatePanel({ countdown, onLeave, status }: RotatePanelProps): TemplateResult {
    return html`<div class="rotate-panel">
        ${rotateIcon()}
        <h2 class="rotate-panel__title">Turn your phone sideways</h2>
        <p class="rotate-panel__hint">The table is played in landscape. The game keeps running meanwhile.</p>
        <span class="connection-status status-${status.tone}" role="status">${status.label}</span>
        ${countdown === null ? "" : countdownTemplate(countdown)}
        <span class="rotate-panel__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>
        <button class="secondary rotate-panel__leave" @click=${onLeave}>Back to Lobby</button>
    </div>`;
}
