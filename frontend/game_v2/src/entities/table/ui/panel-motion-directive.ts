import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import {
    Directive,
    type ElementPart,
    type PartInfo,
    PartType,
    directive,
} from "lit-html/directive.js";

class RevealAfterCall extends Directive {
    render(_afterCall: boolean): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart, [afterCall]: [boolean]): typeof nothing {
        if (afterCall) {
            part.element.classList.add("board-overlay--after-call");
        }
        return nothing;
    }
}

export const revealAfterCall = directive(RevealAfterCall);

class FadeMatchResult extends AsyncDirective {
    private shown = false;
    private animation: Animation | null = null;
    private leaving: HTMLElement | null = null;
    private generation = 0;

    constructor(info: PartInfo) {
        super(info);
        if (info.type !== PartType.ELEMENT) {
            throw new Error("fadeMatchResult belongs on an element");
        }
    }

    render(_shown: boolean): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart, [shown]: [boolean]): typeof nothing {
        if (shown !== this.shown) {
            this.cancel();
            if (this.shown && part.element instanceof HTMLElement) {
                this.leave(part.element);
            }
            this.shown = shown;
        }
        return nothing;
    }

    private leave(board: HTMLElement): void {
        const clone = board.querySelector(".board-overlay")?.cloneNode(true);
        if (
            !(clone instanceof HTMLElement) ||
            matchMedia("(prefers-reduced-motion: reduce)").matches
        ) {
            return;
        }
        const { generation } = this;
        clone.classList.remove("board-overlay--after-call");
        clone.classList.add("board-overlay--leaving");
        clone.setAttribute("aria-hidden", "true");
        clone.inert = true;
        queueMicrotask(() => {
            if (this.isConnected && this.generation === generation) {
                this.play(board, clone);
            }
        });
    }

    private play(board: HTMLElement, clone: HTMLElement): void {
        this.leaving = clone;
        board.append(clone);
        this.animation = clone.animate([{ opacity: 1 }, { opacity: 0 }], {
            duration: 250,
            easing: "ease-out",
        });
        this.animation.onfinish = () => this.cancel();
    }

    private cancel(): void {
        this.generation += 1;
        this.animation?.cancel();
        this.animation = null;
        this.leaving?.remove();
        this.leaving = null;
    }

    protected override disconnected(): void {
        this.cancel();
    }
}

export const fadeMatchResult = directive(FadeMatchResult);
