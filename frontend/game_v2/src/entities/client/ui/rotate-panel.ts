import { type TemplateResult, html, nothing } from "lit-html";

import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    countdownAnnouncement,
    expiredSentence,
    moveName,
} from "@/entities/client/model/countdown-text";
import { type PlayDisplay } from "@/entities/client/model/play-display";
import { type PlayCommand } from "@/entities/client/model/play-ui";
import { t } from "@/shared/i18n";

import { withSecondsFigure } from "./seconds-figure";
import { FailurePanel, LeaveConfirm } from "./session-panels";

/** What the rotate panel shows, all of it the live board's display: the status, what is owed, the way back, an end. */
export type RotatePanelView = Pick<PlayDisplay, "failure" | "leave" | "owedCountdown" | "status">;

/** What runs on while the rotate panel shows: play and its timer, or a round confirm's timer. */
function runningNote(move: DecisionCountdown["move"]): string {
    const key =
        move === "result" || move === "start"
            ? "game.rotate.timer_runs"
            : "game.rotate.play_continues";
    return t(key, { move: moveName(move) });
}

function secondsLeft(countdown: Extract<DecisionCountdown, { kind: "running" }>): TemplateResult {
    const key =
        countdown.clock?.inBank === true
            ? "game.rotate.bank_seconds_left"
            : "game.rotate.seconds_left";
    const text = t(key, { count: countdown.secondsLeft });
    return withSecondsFigure(text, countdown.secondsLeft, "rotate-panel__seconds");
}

function countdownTemplate(countdown: DecisionCountdown): TemplateResult {
    if (countdown.kind === "expired") {
        return html`<div class="rotate-panel__decision rotate-panel__decision--expired">
            <p>${expiredSentence(countdown.move)}</p>
        </div>`;
    }
    const left =
        countdown.kind === "running"
            ? html`<p class="rotate-panel__countdown" aria-live="off">${secondsLeft(countdown)}</p>`
            : "";
    return html`<div class="rotate-panel__decision">
        <p>${runningNote(countdown.move)}</p>
        ${left}
    </div>`;
}

function rotateIcon(): TemplateResult {
    return html`<svg class="rotate-panel__icon" viewBox="0 0 64 64" aria-hidden="true">
        <rect x="22" y="8" width="20" height="36" rx="3" />
        <path d="M14 50 a20 20 0 0 0 36 0" />
        <path d="M42.8 53.5 L50 50 L51.7 57.8" />
    </svg>`;
}

/**
 * The full-screen notice the live game shows instead of the table in a portrait viewport,
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
        <h2 class="rotate-panel__title">${t("game.rotate.title")}</h2>
        <p class="rotate-panel__hint">${t("game.rotate.hint")}</p>
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
            ${t("common.back_to_lobby")}
        </button>
    </div>`;
}

/** The notice a replay shows instead of its board in a portrait viewport: rotate, or leave for the game history. */
export function ReplayRotatePanel(historyHref: string): TemplateResult {
    return html`<div class="replay-rotate">
        <div class="rotate-panel">
            ${rotateIcon()}
            <h2 class="rotate-panel__title">${t("game.rotate.title")}</h2>
            <p class="rotate-panel__hint">${t("game.rotate.replay_hint")}</p>
            <a class="rotate-panel__leave" href=${historyHref} role="button">
                ${t("common.game_history")}
            </a>
        </div>
    </div>`;
}
