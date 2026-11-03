import { type TemplateResult, html, nothing } from "lit-html";

import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    countdownAnnouncement,
    expiryNote,
    moveName,
} from "@/entities/client/model/countdown-text";
import { type PlayDisplay } from "@/entities/client/model/play-display";
import { type PlayCommand } from "@/entities/client/model/play-ui";

import { FailurePanel, LeaveConfirm } from "./session-panels";

/** What the rotate panel shows, all of it the live board's display: the status, what is owed, the way back, an end. */
export type RotatePanelView = Pick<PlayDisplay, "failure" | "leave" | "owedCountdown" | "status">;

/** What runs on while the rotate panel shows: play and its timer, or the round advance's timer. */
function runningNote(move: DecisionCountdown["move"]): string {
    return move === "result"
        ? "Its timer keeps running while this message is shown."
        : "Play continues, and your timer keeps running while this message is shown.";
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
                      countdown.clock?.inBank === true ? " in your time bank" : ""
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
 * The full-screen notice the live game shows instead of the table in a narrow portrait viewport,
 * shows the session's status for a player, its way back (asking first mid-game, the button kept but hidden while
 * asking, so focus can return to it), and while a decision or a round result's confirm awaits the viewer, that the
 * game and its countdown go on. An end that stopped the session on the page shows why and the way on instead. Only
 * the status line and the countdown's thresholds are live regions.
 */
export function RotatePanel(
    { failure, leave, owedCountdown: countdown, status }: RotatePanelView,
    onCommand: (command: PlayCommand) => void,
): TemplateResult {
    if (failure !== null) {
        return html`<div class="rotate-panel rotate-panel--ended">
            <span class="connection-status status-${status.tone}" role="status">${status.label}</span>
            ${FailurePanel(failure, onCommand)}
        </div>`;
    }
    return html`<div class="rotate-panel">
        ${rotateIcon()}
        <h2 class="rotate-panel__title">Landscape mode required</h2>
        <p class="rotate-panel__hint">Rotate your device or widen the window. The game keeps running meanwhile.</p>
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
