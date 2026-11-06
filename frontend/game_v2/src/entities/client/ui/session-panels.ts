import { type TemplateResult, html } from "lit-html";

import { type PlayCommand } from "@/entities/client/model/play-ui";
import { type FailureDisplay } from "@/entities/client/model/session-end";
import { PANEL_CONTROL_FOCUS_KEY } from "@/entities/table";
import { t } from "@/shared/i18n";
import { focusOnFirstRender, keepTabInside } from "@/shared/ui";

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
        aria-label=${t("game.leave.title")}
        @keydown=${onKeydown}
    >
        <p class="leave-confirm__title">${t("game.leave.title")}</p>
        <p class="leave-confirm__detail">${t("game.leave.detail")}</p>
        <div class="leave-confirm__actions">
            <button type="button" data-focus-key=${PANEL_CONTROL_FOCUS_KEY} class="leave-confirm__stay" ${focusOnFirstRender()} @click=${() => onCommand(STAY)}>
                ${t("game.leave.stay")}
            </button>
            <button type="button" data-focus-key=${PANEL_CONTROL_FOCUS_KEY} class="secondary leave-confirm__leave" @click=${() => onCommand(LEAVE)}>${t("game.leave.leave")}</button>
        </div>
    </div>`;
}

/** An end that stopped the session on the page: why, the way back to the lobby and, when it may help, a reload. */
export function FailurePanel(
    failure: FailureDisplay,
    onCommand: (command: PlayCommand) => void,
): TemplateResult {
    return html`<div class="failure-panel" role="alert">
        <p class="failure-panel__title">${t(failure.title)}</p>
        <p class="failure-panel__detail">${t(failure.detail)}</p>
        <div class="failure-panel__actions">
            ${
                failure.reload
                    ? html`<button type="button" data-focus-key=${PANEL_CONTROL_FOCUS_KEY} class="secondary failure-panel__reload" @click=${() => onCommand(RELOAD)}>
                          ${t("common.reload")}
                      </button>`
                    : ""
            }
            <button type="button" data-focus-key=${PANEL_CONTROL_FOCUS_KEY} class="failure-panel__leave" @click=${() => onCommand(LEAVE)}>${t("common.back_to_lobby")}</button>
        </div>
    </div>`;
}
