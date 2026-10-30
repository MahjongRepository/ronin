import { type TemplateResult, html } from "lit-html";

import { type PlayCommand } from "@/entities/client/model/play-ui";
import { type FailureDisplay } from "@/entities/client/model/session-end";
import { focusOnFirstRender, keepTabInside } from "@/entities/table";

const LEAVE: PlayCommand = { intent: { type: "leave" }, kind: "intent" };
const STAY: PlayCommand = { kind: "cancel_leave" };
const RELOAD: PlayCommand = { kind: "reload" };

/**
 * The question leaving mid-game asks, modal while the page makes the rest inert: Stay, the safe default, is the
 * primary action and takes the focus, Tab stays among its buttons, Escape stays too, and Leave is the secondary,
 * destructive one.
 */
export function LeaveConfirm(onCommand: (command: PlayCommand) => void): TemplateResult {
    function onKeydown(event: KeyboardEvent): void {
        if (event.key === "Tab") {
            keepTabInside(event);
            return;
        }
        if (event.key === "Escape") {
            event.preventDefault();
            onCommand(STAY);
        }
    }
    return html`<div
        class="leave-confirm"
        role="alertdialog"
        aria-modal="true"
        aria-label="Leave the game?"
        @keydown=${onKeydown}
    >
        <p class="leave-confirm__title">Leave the game?</p>
        <p class="leave-confirm__detail">An AI will play your seat.</p>
        <div class="leave-confirm__actions">
            <button type="button" class="leave-confirm__stay" ${focusOnFirstRender()} @click=${() => onCommand(STAY)}>
                Stay
            </button>
            <button type="button" class="secondary leave-confirm__leave" @click=${() => onCommand(LEAVE)}>Leave</button>
        </div>
    </div>`;
}

/** An end that stopped the session on the page: why, the way back to the lobby and, when it may help, a reload. */
export function FailurePanel(
    failure: FailureDisplay,
    onCommand: (command: PlayCommand) => void,
): TemplateResult {
    return html`<div class="failure-panel" role="alert">
        <p class="failure-panel__title">${failure.title}</p>
        <p class="failure-panel__detail">${failure.detail}</p>
        <div class="failure-panel__actions">
            ${
                failure.reload
                    ? html`<button type="button" class="secondary failure-panel__reload" @click=${() => onCommand(RELOAD)}>
                          Reload
                      </button>`
                    : ""
            }
            <button type="button" class="failure-panel__leave" @click=${() => onCommand(LEAVE)}>Back to lobby</button>
        </div>
    </div>`;
}
