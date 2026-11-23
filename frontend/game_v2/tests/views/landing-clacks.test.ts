import { describe, expect, it } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import { type SoundCue } from "@/entities/client";
import { DISCARD_LANDING_MS, DRAW_HOLD_MS, OWN_DRAW_HOLD_MS } from "@/entities/table";
import { LandingClacks } from "@/views/landing-clacks";

function heardBy(
    clock: ManualClock,
    played: readonly SoundCue[],
    times: readonly number[],
): readonly SoundCue[][] {
    return times.map((at) => {
        clock.advanceTo(at);
        return [...played];
    });
}

describe("LandingClacks", () => {
    it.each([
        { atLanding: true, clackAt: DISCARD_LANDING_MS, hold: DRAW_HOLD_MS, ownDraw: false },
        { atLanding: false, clackAt: 0, hold: DRAW_HOLD_MS, ownDraw: false },
        { atLanding: true, clackAt: DISCARD_LANDING_MS, hold: OWN_DRAW_HOLD_MS, ownDraw: true },
    ])(
        "ticks a draw that follows a discard only once the hold after its clack passes (clack at landing: $atLanding, own draw: $ownDraw)",
        ({ atLanding, clackAt, hold, ownDraw }) => {
            const clock = new ManualClock();
            const played: SoundCue[] = [];
            const clacks = new LandingClacks(steadyClockOn(clock), {
                play: (cue) => played.push(cue),
                setting: { load: () => ({ sound_on: true }), save: () => {} },
            });

            clacks.play(["discard"], atLanding, false);
            clacks.play(["draw"], atLanding, ownDraw);

            expect(heardBy(clock, played, [clackAt, clackAt + hold - 1, clackAt + hold])).toEqual([
                ["discard"],
                ["discard"],
                ["discard", "draw"],
            ]);
        },
    );
});
