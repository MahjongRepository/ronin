import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import { planTileMotion } from "@/entities/table/lib/board-motion";
import { type BoardDisplayState, type BoardMotionCue } from "@/entities/table/model/board-types";

import { BoardMotionPlayer } from "./board-motion-player";
import { type TileSnapshot, snapshotTiles } from "./board-motion-snapshot";

/** Whether the board animates, and whom it tells when each discard's picture lands. */
interface MotionSwitch {
    readonly animationsOn: boolean;
    readonly onDiscardLanding?: (inMs: number) => void;
}

interface PendingMotion {
    readonly before: readonly TileSnapshot[];
    readonly enabled: boolean;
}

class AnimateBoard extends AsyncDirective {
    private board: HTMLElement | null = null;
    private state: BoardDisplayState | null = null;
    private cue: BoardMotionCue | undefined;
    private queued: PendingMotion | null = null;
    private player: BoardMotionPlayer | null = null;
    private media: MediaQueryList | null = null;
    private observer: ResizeObserver | null = null;
    private size = "";
    private renderVersion = 0;
    private animationsOn = true;

    constructor(info: PartInfo) {
        super(info);
        if (info.type !== PartType.ELEMENT) {
            throw new Error("animateBoard belongs on an element");
        }
    }

    render(
        _state: BoardDisplayState | null,
        _cue: BoardMotionCue | undefined,
        _motion: MotionSwitch,
    ): typeof nothing {
        return nothing;
    }

    override update(
        part: ElementPart,
        [state, cue, { animationsOn, onDiscardLanding }]: Parameters<AnimateBoard["render"]>,
    ): typeof nothing {
        if (!(part.element instanceof HTMLElement)) {
            return nothing;
        }
        this.board = part.element;
        this.player ??= new BoardMotionPlayer(part.element);
        this.player.onDiscardLanding = onDiscardLanding;
        this.followSwitch(animationsOn);
        this.player.prepareRender();
        this.updateState(state, cue);
        this.finishRender();
        return nothing;
    }

    private followSwitch(animationsOn: boolean): void {
        if (this.animationsOn && !animationsOn) {
            this.cancel();
        }
        this.animationsOn = animationsOn;
    }

    private finishRender(): void {
        const version = ++this.renderVersion;
        queueMicrotask(() => {
            if (
                version === this.renderVersion &&
                this.isConnected &&
                this.board?.isConnected === true
            ) {
                this.player?.finishRender();
            }
        });
    }

    private updateState(state: BoardDisplayState | null, cue: BoardMotionCue | undefined): void {
        const previous = { cue: this.cue, state: this.state };
        this.state = state;
        this.cue = cue;
        if (
            previous.state?.motionContext !== state?.motionContext ||
            previous.cue?.sequence !== cue?.sequence ||
            previous.cue?.mode !== cue?.mode
        ) {
            this.schedule(previous.state, previous.cue);
        }
    }

    private schedule(
        previous: BoardDisplayState | null,
        priorCue: BoardMotionCue | undefined,
    ): void {
        const { board, cue, state } = this;
        this.observe();
        const enabled =
            state !== null &&
            previous !== null &&
            cue !== undefined &&
            cue.mode !== "reset" &&
            priorCue !== undefined &&
            cue.sequence === priorCue.sequence + 1 &&
            previous.motionContext === state.motionContext &&
            this.motionAllowed(board);
        const continuesRound = enabled && previous.motionRound === state.motionRound;
        if (!continuesRound || cue?.mode === "replay") {
            this.cancel();
        }
        const frame = { before: this.motionSources(board, continuesRound, cue), enabled };
        this.queued = frame;
        queueMicrotask(() => this.commit(frame));
    }

    private motionSources(
        board: HTMLElement | null,
        continuesRound: boolean,
        cue: BoardMotionCue | undefined,
    ): readonly TileSnapshot[] {
        if (!continuesRound || board === null) {
            return [];
        }
        const priorFrame =
            cue?.mode !== "replay" && this.queued?.enabled === true ? this.queued : null;
        return priorFrame?.before ?? snapshotTiles(board);
    }

    private commit(frame: PendingMotion): void {
        if (frame !== this.queued || !this.isConnected || this.board?.isConnected !== true) {
            return;
        }
        this.queued = null;
        this.animate(frame);
    }

    private animate({ before, enabled }: PendingMotion): void {
        const { board } = this;
        if (!enabled || this.state === null || !this.motionAllowed(board)) {
            return;
        }
        const after = snapshotTiles(board);
        this.player?.play(planTileMotion(before, after, this.cue?.mode), before, after);
    }

    private motionAllowed(board: HTMLElement | null): board is HTMLElement {
        return (
            board !== null &&
            this.animationsOn &&
            this.media?.matches !== true &&
            typeof board.animate === "function"
        );
    }

    private observe(): void {
        if (this.media === null && typeof matchMedia === "function") {
            this.media = matchMedia("(prefers-reduced-motion: reduce)");
            this.media.addEventListener("change", this.cancel);
        }
        if (
            this.observer !== null ||
            this.board === null ||
            typeof ResizeObserver === "undefined"
        ) {
            return;
        }
        const box = this.board.getBoundingClientRect();
        this.size = `${box.width}:${box.height}`;
        this.observer = new ResizeObserver((entries) => {
            const rect = entries.at(-1)?.contentRect;
            if (rect === undefined) {
                return;
            }
            const next = `${rect.width}:${rect.height}`;
            if (this.size !== next) {
                this.size = next;
                this.cancel();
            }
        });
        this.observer.observe(this.board);
    }

    private readonly cancel = (): void => {
        this.player?.cancel();
    };

    protected override disconnected(): void {
        this.queued = null;
        this.cancel();
        this.observer?.disconnect();
        this.observer = null;
        this.media?.removeEventListener("change", this.cancel);
        this.media = null;
        this.cue = undefined;
    }
}

export const animateBoard = directive(AnimateBoard);
