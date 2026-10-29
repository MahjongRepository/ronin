import { type TemplateResult, html, nothing } from "lit-html";
import {
    Directive,
    type ElementPart,
    type PartInfo,
    PartType,
    directive,
} from "lit-html/directive.js";

import { type FailureDisplay, type PlayCommand } from "@/entities/client/model/play-display";

const LEAVE: PlayCommand = { intent: { type: "leave" }, kind: "intent" };
const STAY: PlayCommand = { kind: "cancel_leave" };
const RELOAD: PlayCommand = { kind: "reload" };

/**
 * Focus the element it sits on once, when it first renders, after the render has put it in the document. A copy
 * the page hides takes no focus, so the visible one of two copies keeps it.
 */
class FocusOnFirstRender extends Directive {
    private focused = false;

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("focusOnFirstRender belongs on an element");
        }
    }

    render(): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart): typeof nothing {
        if (!this.focused) {
            this.focused = true;
            const { element } = part;
            queueMicrotask(() => {
                if (element instanceof HTMLElement) {
                    element.focus();
                }
            });
        }
        return nothing;
    }
}

const focusOnFirstRender = directive(FocusOnFirstRender);

/**
 * The question leaving mid-game asks, modal while the page makes the rest inert: Stay, the safe default, is the
 * primary action and takes the focus, Escape stays too, and Leave is the secondary, destructive one.
 */
export function LeaveConfirm(onCommand: (command: PlayCommand) => void): TemplateResult {
    function onKeydown(event: KeyboardEvent): void {
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
