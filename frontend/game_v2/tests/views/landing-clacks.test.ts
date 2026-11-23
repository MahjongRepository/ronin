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

const LANDS_AT = 30 + DISCARD_LANDING_MS;

function listen(): { clacks: LandingClacks; clock: ManualClock; played: SoundCue[] } {
    const clock = new ManualClock();
    const played: SoundCue[] = [];
    const clacks = new LandingClacks(steadyClockOn(clock), {
        play: (cue) => played.push(cue),
        setting: { load: () => ({ sound_on: true }), save: () => {} },
    });
    return { clacks, clock, played };
}

function landAt(clock: ManualClock, clacks: LandingClacks, at: number): void {
    clock.advanceTo(at);
    clacks.landIn(DISCARD_LANDING_MS);
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

    it("moves a waiting clack and only the draw tick waiting on it to the landing the board reports", () => {
        const { clacks, clock, played } = listen();

        clacks.play(["discard"], true, false);
        clacks.play(["draw"], true, false);
        landAt(clock, clacks, 30);
        const first = heardBy(clock, played, [LANDS_AT - 1, LANDS_AT]);
        clock.advanceTo(200);
        clacks.play(["discard"], true, false);
        landAt(clock, clacks, 230);

        expect([
            first,
            heardBy(clock, played, [
                230 + DISCARD_LANDING_MS,
                LANDS_AT + DRAW_HOLD_MS - 1,
                LANDS_AT + DRAW_HOLD_MS,
            ]),
        ]).toEqual([
            [[], ["discard"]],
            [
                ["discard", "discard"],
                ["discard", "discard"],
                ["discard", "discard", "draw"],
            ],
        ]);
    });
});
