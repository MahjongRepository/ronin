export interface SoundSamples {
    readonly samples: Float32Array<ArrayBuffer>;
    readonly sampleRate: number;
}

export type SoundSource = (
    | { readonly kind: "file"; readonly url: string }
    | ({ readonly kind: "generated" } & SoundSamples)
) & { readonly volume: number };

/**
 * Where a player's sounds play: a file loaded into a clip; `ready` resolving once a clip can start, which rejects with a
 * `NotAllowedError` before the page's first user gesture; and a clip started at a volume over any play still going.
 */
export interface SoundOutput<Clip> {
    readonly load: (source: SoundSource) => Promise<Clip>;
    readonly ready: () => Promise<void>;
    readonly start: (clip: Clip, volume: number) => void;
}

/** Plays a named sound, each play its own, so plays close together overlap rather than cut each other off. */
export interface SoundPlayer<Name extends string> {
    readonly play: (name: Name) => void;
}

const LATE_PLAY_DROP_MS = 500;

type ClipState<Clip> =
    | { readonly kind: "loading" }
    | { readonly kind: "failed" }
    | { readonly kind: "loaded"; readonly clip: Clip };

/**
 * A player of the sounds `sources` names, each loaded as the player is made; a sound still loading is skipped, and one
 * whose load failed (reported on the console) is skipped and loaded again. A play the browser refuses before the page's
 * first user gesture (a page reloaded mid-game) is skipped too, as is one the output became ready for too late to still
 * match its move; any other failure is reported on the console.
 */
export function createSoundPlayer<Name extends string, Clip>(
    sources: Readonly<Record<Name, SoundSource>>,
    output: SoundOutput<Clip>,
    now: () => number,
): SoundPlayer<Name> {
    const clips = new Map<string, ClipState<Clip>>();
    function load(name: string, source: SoundSource): void {
        clips.set(name, { kind: "loading" });
        output.load(source).then(
            (clip) => clips.set(name, { clip, kind: "loaded" }),
            (error: unknown) => {
                clips.set(name, { kind: "failed" });
                console.error(`The sound "${name}" failed to load:`, error);
            },
        );
    }
    for (const [name, source] of Object.entries<SoundSource>(sources)) {
        load(name, source);
    }
    return {
        play: (name) => {
            if (!Object.hasOwn(sources, name)) {
                throw new Error(`No sound named "${name}"`);
            }
            const state = clips.get(name);
            if (state?.kind === "failed") {
                load(name, sources[name]);
            }
            if (state?.kind !== "loaded") {
                return;
            }
            const requestedAt = now();
            output
                .ready()
                .then(() => {
                    if (now() - requestedAt <= LATE_PLAY_DROP_MS) {
                        output.start(state.clip, sources[name].volume);
                    }
                })
                .catch((error: unknown) => {
                    if (!(error instanceof DOMException && error.name === "NotAllowedError")) {
                        console.error(`The sound "${name}" failed to play:`, error);
                    }
                });
        },
    };
}
