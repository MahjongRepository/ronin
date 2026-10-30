import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
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

/** Whether a player can see and reach an element of the board: shown, visible and outside anything inert. */
function isReachable(element: Element, board: Element): boolean {
    const disabled = element.matches(":disabled");
    if (
        disabled ||
        getComputedStyle(element).visibility === "hidden" ||
        element.closest("[inert]") !== null
    ) {
        return false;
    }
    for (
        let node: Element | null = element;
        node !== null && node !== board;
        node = node.parentElement
    ) {
        if (getComputedStyle(node).display === "none") {
            return false;
        }
    }
    return true;
}

/**
 * Give a focus the page lost back to the board: the first reachable, enabled element `targets` names, in their order,
 * that takes it, else the board itself, made focusable for it (never in the Tab order). A focus something took
 * meanwhile (an end's or the leave question's own) is left alone.
 */
function refocusBoard(board: Element, targets: readonly string[]): void {
    const page = board.ownerDocument;
    if (!board.isConnected || (page.activeElement !== null && page.activeElement !== page.body)) {
        return;
    }
    const candidates = targets
        .flatMap((selector) => [...board.querySelectorAll<HTMLElement>(selector)])
        .filter((element) => isReachable(element, board));
    const taken = candidates.some((element) => {
        element.focus();
        return page.activeElement === element;
    });
    if (!taken && board instanceof HTMLElement) {
        board.tabIndex = -1;
        board.focus();
    }
}

/**
 * On the element of a modal over the board: once it leaves the page (closed by its control, by a key, or by the state
 * moving on), and every other render's focus has settled (a clamp, a panel's own focus), give the focus back to the
 * board if it fell to the page's body (`refocusBoard`, with its targets).
 */
class FocusBackOnClose extends AsyncDirective {
    private board: Element | null = null;
    private targets: readonly string[] = [];

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("focusBackOnClose belongs on an element");
        }
    }

    render(_targets: readonly string[]): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart, [targets]: [readonly string[]]): typeof nothing {
        this.targets = targets;
        const { element } = part;
        queueMicrotask(() => {
            this.board = element.closest(".game-board") ?? this.board;
        });
        return nothing;
    }

    protected override disconnected(): void {
        const { board, targets } = this;
        if (board !== null) {
            queueMicrotask(() => queueMicrotask(() => refocusBoard(board, targets)));
        }
    }
}

export const focusBackOnClose = directive(FocusBackOnClose);

/** Keep Tab and Shift+Tab cycling through a modal's buttons, so the focus never leaves it for the page beyond. */
export function keepTabInside(event: KeyboardEvent): void {
    const modal = event.currentTarget;
    if (!(modal instanceof HTMLElement)) {
        return;
    }
    const buttons = [...modal.querySelectorAll("button")];
    const edge = event.shiftKey ? buttons[0] : buttons.at(-1);
    const wrapTo = event.shiftKey ? buttons.at(-1) : buttons[0];
    if (edge === undefined || wrapTo === undefined || document.activeElement !== edge) {
        return;
    }
    event.preventDefault();
    wrapTo.focus();
}
