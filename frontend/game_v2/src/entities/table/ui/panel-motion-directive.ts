import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import {
    Directive,
    type ElementPart,
    type PartInfo,
    PartType,
    directive,
} from "lit-html/directive.js";

class HoldPanel extends Directive {
    private decided = false;

    render(_held: boolean): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart, [held]: [boolean]): typeof nothing {
        if (!this.decided && held) {
            part.element.classList.add("board-overlay--held");
        }
        this.decided = true;
        return nothing;
    }
}

export const holdPanel = directive(HoldPanel);

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

    render(_shown: boolean, _animationsOn: boolean): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart, [shown, animationsOn]: [boolean, boolean]): typeof nothing {
        if (shown !== this.shown) {
            this.cancel();
            if (this.shown && animationsOn && part.element instanceof HTMLElement) {
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
        clone.classList.remove(
            "board-overlay--held",
            "board-overlay--peekable",
            "board-overlay--peeking",
        );
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
