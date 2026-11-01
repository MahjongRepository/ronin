import { nothing } from "lit-html";
import {
    Directive,
    type ElementPart,
    type PartInfo,
    PartType,
    directive,
} from "lit-html/directive.js";

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

export const focusOnFirstRender = directive(FocusOnFirstRender);

/** Keep Tab and Shift+Tab cycling through a modal's buttons, so the focus never leaves it for the page beyond. */
export function keepTabInside(event: KeyboardEvent): void {
    const modal = event.currentTarget;
    if (!(modal instanceof HTMLElement)) {
        return;
    }
    const buttons = [...modal.querySelectorAll("button")];
    const edge = event.shiftKey ? buttons[0] : buttons.at(-1);
    const wrapTo = event.shiftKey ? buttons.at(-1) : buttons[0];
    if (edge === undefined || wrapTo === undefined || modal.ownerDocument.activeElement !== edge) {
        return;
    }
    event.preventDefault();
    wrapTo.focus();
}
