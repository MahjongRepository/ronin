import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

const OVERLAY_SELECTOR = ".board-overlay";
const PEEKABLE_CLASS = "board-overlay--peekable";
const PEEKING_CLASS = "board-overlay--peeking";

/**
 * On a panel's root: a press on the board's overlay beside the panel hides the panel and the dim to show the board
 * under it until the press ends. The panel finds the overlay it stands in once it is in the page.
 */
class PeekWhilePressed extends AsyncDirective {
    private panel: Element | null = null;
    private overlay: HTMLElement | null = null;
    private listeners: AbortController | null = null;
    private pointerId: number | null = null;

    constructor(info: PartInfo) {
        super(info);
        if (info.type !== PartType.ELEMENT) {
            throw new Error("peekWhilePressed belongs on an element");
        }
    }

    render(): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart): typeof nothing {
        this.panel = part.element;
        if (this.overlay === null || !this.overlay.contains(part.element)) {
            queueMicrotask(() => this.bind());
        }
        return nothing;
    }

    private bind(): void {
        const overlay = this.isConnected
            ? (this.panel?.closest<HTMLElement>(OVERLAY_SELECTOR) ?? null)
            : null;
        if (overlay === this.overlay) {
            return;
        }
        this.unbind();
        if (overlay === null) {
            return;
        }
        this.overlay = overlay;
        this.listen(overlay);
        overlay.classList.add(PEEKABLE_CLASS);
    }

    private listen(overlay: HTMLElement): void {
        this.listeners = new AbortController();
        const options = { signal: this.listeners.signal };
        overlay.addEventListener("pointerdown", this.onPointerdown, options);
        overlay.addEventListener("pointerup", this.onPointerEnd, options);
        overlay.addEventListener("pointercancel", this.onPointerEnd, options);
        overlay.addEventListener("lostpointercapture", this.onPointerEnd, options);
        overlay.addEventListener("contextmenu", this.onContextmenu, options);
    }

    private unbind(): void {
        this.listeners?.abort();
        this.listeners = null;
        this.pointerId = null;
        this.overlay?.classList.remove(PEEKABLE_CLASS, PEEKING_CLASS);
        this.overlay = null;
    }

    private readonly onPointerdown = (event: PointerEvent): void => {
        const { overlay } = this;
        if (
            overlay === null ||
            event.target !== overlay ||
            !event.isPrimary ||
            event.button !== 0
        ) {
            return;
        }
        this.pointerId = event.pointerId;
        overlay.classList.add(PEEKING_CLASS);
        overlay.setPointerCapture(event.pointerId);
    };

    private readonly onPointerEnd = (event: PointerEvent): void => {
        if (event.pointerId !== this.pointerId) {
            return;
        }
        this.pointerId = null;
        this.overlay?.classList.remove(PEEKING_CLASS);
    };

    private readonly onContextmenu = (event: MouseEvent): void => {
        if (event.target === this.overlay || this.pointerId !== null) {
            event.preventDefault();
        }
    };

    protected override disconnected(): void {
        this.unbind();
    }

    protected override reconnected(): void {
        queueMicrotask(() => this.bind());
    }
}

export const peekWhilePressed = directive(PeekWhilePressed);
