import { type GameSound, type SoundCue } from "@/entities/client";
import { DISCARD_LANDING_MS, DRAW_HOLD_MS, OWN_DRAW_HOLD_MS } from "@/entities/table";
import { type CancelTimer, type Clock } from "@/shared/clock";

interface PendingCues {
    readonly at: number;
    readonly cancel: CancelTimer;
    readonly lead: SoundCue;
    readonly cues: SoundCue[];
    /** The waiting clack this tick follows, which moves it along. */
    readonly follows: PendingCues | null;
}

export class LandingClacks {
    private readonly clock: Clock;
    private readonly sound: GameSound;
    private pending: readonly PendingCues[] = [];
    private clackAt: number | null = null;

    constructor(clock: Clock, sound: GameSound) {
        this.clock = clock;
        this.sound = sound;
    }

    /** Play a step's cues, its draw's tick as its tile shows: the own hand's draw hold after the latest clack when `ownDraw`. */
    play(cues: readonly SoundCue[], clackAtLanding: boolean, ownDraw: boolean): void {
        for (const cue of cues) {
            const landing = this.pending.findLast((pending) => pending.lead === "discard");
            if (cue === "discard") {
                this.clack(clackAtLanding);
            } else if (cue === "draw") {
                this.drawAfterClack(ownDraw ? OWN_DRAW_HOLD_MS : DRAW_HOLD_MS);
            } else if (cue === "decision" && landing !== undefined) {
                landing.cues.push(cue);
            } else {
                this.sound.play(cue);
            }
        }
    }

    /** Move the waiting clack, and the ticks waiting on it, to the board's landing `inMs` from now. */
    landIn(inMs: number): void {
        const clack = this.pending.findLast((pending) => pending.lead === "discard");
        if (clack === undefined) {
            return;
        }
        const shift = this.clock.now() + inMs - clack.at;
        this.clackAt = clack.at + shift;
        const ticks = this.pending.filter((pending) => pending.follows === clack);
        this.drop([clack, ...ticks]);
        const moved = this.playLater(clack.at + shift - this.clock.now(), clack.lead, clack);
        for (const tick of ticks) {
            this.playLater(tick.at + shift - this.clock.now(), tick.lead, {
                ...tick,
                follows: moved,
            });
        }
    }

    private drop(dropped: readonly PendingCues[]): void {
        for (const pending of dropped) {
            pending.cancel();
        }
        this.pending = this.pending.filter((pending) => !dropped.includes(pending));
    }

    landNow(): void {
        const landings = this.pending.filter((pending) => pending.lead === "discard");
        if (landings.length === 0) {
            return;
        }
        const waiting = this.pending.filter((pending) => pending.lead !== "discard");
        this.cancel();
        this.clackAt = this.clock.now();
        for (const landing of landings) {
            landing.cues.forEach(this.sound.play);
        }
        for (const pending of waiting) {
            pending.cues.forEach((cue) => this.playLater(DRAW_HOLD_MS, cue));
        }
    }

    cancel(): void {
        for (const pending of this.pending) {
            pending.cancel();
        }
        this.pending = [];
        this.clackAt = null;
    }

    private clack(atLanding: boolean): void {
        if (!atLanding) {
            this.clackAt = this.clock.now();
            this.sound.play("discard");
            return;
        }
        this.clackAt = this.clock.now() + DISCARD_LANDING_MS;
        this.playLater(DISCARD_LANDING_MS, "discard");
    }

    private drawAfterClack(drawHoldMs: number): void {
        const wait = this.clackAt === null ? 0 : this.clackAt + drawHoldMs - this.clock.now();
        if (wait > 0) {
            const clack = this.pending.findLast((pending) => pending.lead === "discard");
            this.playLater(wait, "draw", { follows: clack ?? null });
        } else {
            this.sound.play("draw");
        }
    }

    private playLater(
        delayMs: number,
        lead: SoundCue,
        { cues = [lead], follows = null }: Partial<Pick<PendingCues, "cues" | "follows">> = {},
    ): PendingCues {
        const pending: PendingCues = {
            at: this.clock.now() + delayMs,
            cancel: this.clock.setTimer(delayMs, () => {
                this.pending = this.pending.filter((other) => other !== pending);
                cues.forEach(this.sound.play);
            }),
            cues,
            follows,
            lead,
        };
        this.pending = [...this.pending, pending];
        return pending;
    }
}
