export interface SoundSamples {
    readonly samples: Float32Array<ArrayBuffer>;
    readonly sampleRate: number;
}

export type SoundSource = (
    | { readonly kind: "file"; readonly url: string }
    | ({ readonly kind: "generated" } & SoundSamples)
) & { readonly volume: number };

/**
 * Where a player's sounds play: a file loaded into a clip, and a clip started at a volume over any play still going,
 * which rejects with a `NotAllowedError` before the page's first user gesture.
 */
export interface SoundOutput<Clip> {
    readonly load: (source: SoundSource) => Promise<Clip>;
    readonly start: (clip: Clip, volume: number) => Promise<void>;
}

/** Plays a named sound, each play its own, so plays close together overlap rather than cut each other off. */
export interface SoundPlayer<Name extends string> {
    readonly play: (name: Name) => void;
}

/**
 * A player of the sounds `sources` names, each loaded as the player is made; a sound still loading, or whose load
 * failed (reported on the console), is skipped. A play the browser refuses before the page's first user gesture (a
 * page reloaded mid-game) is skipped too; any other failure is reported on the console.
 */
export function createSoundPlayer<Name extends string, Clip>(
    sources: Readonly<Record<Name, SoundSource>>,
    output: SoundOutput<Clip>,
): SoundPlayer<Name> {
    const clips = new Map<string, Clip>();
    for (const [name, source] of Object.entries<SoundSource>(sources)) {
        output.load(source).then(
            (clip) => clips.set(name, clip),
            (error: unknown) => console.error(`The sound "${name}" failed to load:`, error),
        );
    }
    return {
        play: (name) => {
            if (!Object.hasOwn(sources, name)) {
                throw new Error(`No sound named "${name}"`);
            }
            const clip = clips.get(name);
            if (clip === undefined) {
                return;
            }
            output.start(clip, sources[name].volume).catch((error: unknown) => {
                if (!(error instanceof DOMException && error.name === "NotAllowedError")) {
                    console.error(`The sound "${name}" failed to play:`, error);
                }
            });
        },
    };
}
