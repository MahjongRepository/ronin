import { type TemplateResult, html, nothing } from "lit-html";

import { type DecisionCountdown, pendingCountdown } from "@/entities/client/model/countdown";
import {
    type FailureDisplay,
    type LeaveControls,
    type PlayCommand,
    type PlayUi,
    failureDisplay,
    leaveControls,
} from "@/entities/client/model/play-display";
import { type GameClientState } from "@/entities/client/model/types";
import {
    type SessionStatusDisplay,
    describePlayerSessionStatus,
    describeSessionStatus,
} from "@/entities/session";
import { assertNever } from "@/shared/lib";
import { CONNECTION_STATUS } from "@/shared/protocol";

import { FailurePanel, LeaveConfirm } from "./session-panels";

const NO_SESSION_STATUS: SessionStatusDisplay = {
    label: "No session",
    tone: CONNECTION_STATUS.ERROR,
    word: "Error",
};

const NOT_CONNECTED_STATUS: SessionStatusDisplay = {
    label: "Not connected",
    tone: CONNECTION_STATUS.ERROR,
    word: "Error",
};

/** The seconds left at which the countdown is announced to a screen reader, the largest first. */
const ANNOUNCED_SECONDS = [10, 5] as const;

export interface RotatePanelProps {
    readonly status: SessionStatusDisplay;
    readonly countdown: DecisionCountdown | null;
    readonly leave: LeaveControls;
    /** An end that stopped the session on the page, shown in place of the rest: why, and the way on from it. */
    readonly failure: FailureDisplay | null;
    readonly onCommand: (command: PlayCommand) => void;
}

/** The session's status line for a live client's state, in the machine's own terms, for the debug view. */
export function describeClientStatus(state: GameClientState): SessionStatusDisplay {
    return state.session === null ? NO_SESSION_STATUS : describeSessionStatus(state.session);
}

/** The session's status in a player's terms, for the live page and its rotate panel. */
export function describePlayerClientStatus(state: GameClientState): SessionStatusDisplay {
    return state.session === null
        ? NOT_CONNECTED_STATUS
        : describePlayerSessionStatus(state.session);
}

export function rotatePanelProps(
    state: GameClientState,
    ui: PlayUi,
    onCommand: (command: PlayCommand) => void,
): RotatePanelProps {
    return {
        countdown: pendingCountdown(state),
        failure: failureDisplay(state.session),
        leave: leaveControls(state, ui),
        onCommand,
        status: describePlayerClientStatus(state),
    };
}

function moveName(move: DecisionCountdown["move"]): string {
    switch (move) {
        case "turn": {
            return "It is your turn";
        }
        case "call": {
            return "You can call the last discard";
        }
        case "chankan": {
            return "You can rob the kan";
        }
        case "result": {
            return "The round's result awaits your OK";
        }
        default: {
            return assertNever(move);
        }
    }
}

/** What runs on while the phone is upright: play and its timer, or the round advance's timer. */
function runningNote(move: DecisionCountdown["move"]): string {
    return move === "result"
        ? "Its timer keeps running while the phone is upright."
        : "Play continues, and your timer keeps running while the phone is upright.";
}

/** What the server does once the move's time is up. */
function expiryNote(move: DecisionCountdown["move"]): string {
    return move === "result" ? "the server deals the next round" : "the server makes the move";
}

/**
 * What the polite live region says: it changes only when the countdown crosses a threshold, a turn's base time runs
 * out into its bank, or it expires, so a screen reader is not read the seconds every second.
 */
export function countdownAnnouncement(countdown: DecisionCountdown | null): string {
    if (countdown?.kind === "expired") {
        return "Time is up";
    }
    if (countdown?.kind !== "running") {
        return "";
    }
    const crossed = ANNOUNCED_SECONDS.findLast((seconds) => countdown.secondsLeft <= seconds);
    if (crossed !== undefined) {
        return `${crossed} seconds or less left`;
    }
    return countdown.turn?.inBank === true ? "Your time bank is running" : "";
}

function countdownTemplate(countdown: DecisionCountdown): TemplateResult {
    if (countdown.kind === "expired") {
        return html`<div class="rotate-panel__decision rotate-panel__decision--expired">
            <p>${moveName(countdown.move)}, and its time is up: ${expiryNote(countdown.move)}.</p>
        </div>`;
    }
    const left =
        countdown.kind === "running"
            ? html`<p class="rotate-panel__countdown" aria-live="off">
                  <span class="rotate-panel__seconds">${countdown.secondsLeft}</span> s left${
                      countdown.turn?.inBank === true ? " in your time bank" : ""
                  }
              </p>`
            : "";
    return html`<div class="rotate-panel__decision">
        <p>${moveName(countdown.move)}. ${runningNote(countdown.move)}</p>
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
 * shows the session's status for a player, its way back (asking first mid-game, the button kept but hidden while
 * asking, so focus can return to it), and while a decision or a round result's confirm awaits the viewer, that the
 * game and its countdown go on. An end that stopped the session on the page shows why and the way on instead. Only
 * the status line and the countdown's thresholds are live regions.
 */
export function RotatePanel({
    countdown,
    failure,
    leave,
    onCommand,
    status,
}: RotatePanelProps): TemplateResult {
    if (failure !== null) {
        return html`<div class="rotate-panel rotate-panel--ended">
            <span class="connection-status status-${status.tone}" role="status">${status.label}</span>
            ${FailurePanel(failure, onCommand)}
        </div>`;
    }
    return html`<div class="rotate-panel">
        ${rotateIcon()}
        <h2 class="rotate-panel__title">Turn your phone sideways</h2>
        <p class="rotate-panel__hint">The table is played in landscape. The game keeps running meanwhile.</p>
        <span class="connection-status status-${status.tone}" role="status">${status.label}</span>
        ${countdown === null ? "" : countdownTemplate(countdown)}
        <span class="rotate-panel__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>
        ${leave.confirming ? LeaveConfirm(onCommand) : ""}
        <button
            class="secondary rotate-panel__leave"
            ?hidden=${leave.confirming}
            aria-haspopup=${leave.command.kind === "ask_leave" ? "dialog" : nothing}
            @click=${() => onCommand(leave.command)}
        >
            Back to lobby
        </button>
    </div>`;
}
