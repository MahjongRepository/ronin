import { describe, expect, it, onTestFinished, vi } from "vitest";

import { type SoundOutput, type SoundSource, createSoundPlayer } from "@/shared/lib";

interface Pending {
    readonly resolve: () => void;
    readonly reject: (error: Error) => void;
}

/** An output whose loads and readiness wait until the test settles them, recording each load and start. */
function fakeOutput(): {
    readonly output: SoundOutput<string>;
    readonly loads: Pending[];
    readonly readies: Pending[];
    readonly started: (readonly [string, number])[];
} {
    const loads: Pending[] = [];
    const readies: Pending[] = [];
    const started: (readonly [string, number])[] = [];
    const output: SoundOutput<string> = {
        load: (source) => {
            if (source.kind !== "file") {
                throw new Error("Expected a file");
            }
            return new Promise((resolve, reject) => {
                loads.push({ reject, resolve: () => resolve(`clip:${source.url}`) });
            });
        },
        ready: () =>
            new Promise((resolve, reject) => {
                readies.push({ reject, resolve });
            }),
        start: (clip, volume) => {
            started.push([clip, volume]);
        },
    };
    return { loads, output, readies, started };
}

/** Run `act`, then let every promise it settled run its handlers. */
async function settle(act: () => void): Promise<void> {
    act();
    await new Promise((resolve) => {
        setTimeout(resolve, 0);
    });
}

function silenceConsoleError(): ReturnType<typeof vi.spyOn> {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    onTestFinished(() => consoleError.mockRestore());
    return consoleError;
}

const RON = { ron: { kind: "file", url: "/ron.wav", volume: 0.2 } } satisfies Record<
    string,
    SoundSource
>;

describe("createSoundPlayer", () => {
    it("starts every play of a loaded sound at its volume, skips one still loading or blocked before the first gesture, and reports any other failure", async () => {
        const consoleError = silenceConsoleError();
        const readyFailure = new DOMException("x", "AbortError");
        const { loads, output, readies, started } = fakeOutput();
        const player = createSoundPlayer(RON, output, () => 0);

        player.play("ron");
        await settle(() => loads[0]?.resolve());
        await settle(() => (["ron", "ron", "ron"] as const).forEach(player.play));
        await settle(() => {
            readies[0]?.reject(new DOMException("no gesture", "NotAllowedError"));
            readies[1]?.reject(readyFailure);
            readies[2]?.resolve();
        });

        expect([started, consoleError.mock.calls]).toEqual([
            [["clip:/ron.wav", 0.2]],
            [['The sound "ron" failed to play:', readyFailure]],
        ]);
    });

    it("loads a sound whose load failed again at its next play, and starts it once that load succeeds", async () => {
        const consoleError = silenceConsoleError();
        const loadFailure = new Error("503");
        const { loads, output, readies, started } = fakeOutput();
        const player = createSoundPlayer(RON, output, () => 0);

        await settle(() => loads[0]?.reject(loadFailure));
        player.play("ron");
        await settle(() => loads[1]?.resolve());
        player.play("ron");
        await settle(() => readies[0]?.resolve());

        expect([loads.length, started, consoleError.mock.calls]).toEqual([
            2,
            [["clip:/ron.wav", 0.2]],
            [['The sound "ron" failed to load:', loadFailure]],
        ]);
    });

    it("drops a play its output became ready for more than half a second after it was asked, so a resumed output plays no backlog", async () => {
        let now = 0;
        const { loads, output, readies, started } = fakeOutput();
        const player = createSoundPlayer(RON, output, () => now);
        await settle(() => loads[0]?.resolve());

        player.play("ron");
        now = 400;
        player.play("ron");
        now = 800;
        await settle(() => readies.forEach((ready) => ready.resolve()));

        expect(started).toEqual([["clip:/ron.wav", 0.2]]);
    });
});
