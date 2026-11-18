import { type GameSound, type SoundCue } from "@/entities/client";
import { DISCARD_LANDING_MS } from "@/entities/table";
import { type CancelTimer, type Clock } from "@/shared/clock";

export class LandingClacks {
    private readonly clock: Clock;
    private readonly sound: GameSound;
    private readonly pending = new Set<CancelTimer>();

    constructor(clock: Clock, sound: GameSound) {
        this.clock = clock;
        this.sound = sound;
    }

    play(cues: readonly SoundCue[], clackAtLanding: boolean): void {
        for (const cue of cues) {
            if (clackAtLanding && cue === "discard") {
                this.clackAtLanding();
            } else {
                this.sound.play(cue);
            }
        }
    }

    landNow(): void {
        const landing = this.pending.size;
        this.cancel();
        for (let clack = 0; clack < landing; clack += 1) {
            this.sound.play("discard");
        }
    }

    cancel(): void {
        for (const cancelTimer of this.pending) {
            cancelTimer();
        }
        this.pending.clear();
    }

    private clackAtLanding(): void {
        const cancelTimer = this.clock.setTimer(DISCARD_LANDING_MS, () => {
            this.pending.delete(cancelTimer);
            this.sound.play("discard");
        });
        this.pending.add(cancelTimer);
    }
}
