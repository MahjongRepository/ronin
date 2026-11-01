import { type SoundOutput } from "./sound-player";

/** The rate files are decoded at; a clip plays resampled to its context's own. */
const DECODE_SAMPLE_RATE = 44_100;

/**
 * The browser's Web Audio as a player's output: each file fetched and decoded once, each play a source of its own.
 * Files decode offline, and the playing context is made only at the first play after the page's first user gesture
 * (`hasBeenActive`), so no context waits suspended for one and no plays pile up to burst out at it.
 */
export function webAudioOutput(hasBeenActive: () => boolean): SoundOutput<AudioBuffer> {
    const decoder = new OfflineAudioContext(1, 1, DECODE_SAMPLE_RATE);
    let context: AudioContext | null = null;
    return {
        load: async (url) => {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`The sound file ${url} answered ${response.status}`);
            }
            return decoder.decodeAudioData(await response.arrayBuffer());
        },
        start: async (clip, volume) => {
            if (!hasBeenActive()) {
                throw new DOMException("No user gesture yet", "NotAllowedError");
            }
            context ??= new AudioContext();
            if (context.state !== "running") {
                await context.resume();
            }
            const gain = new GainNode(context, { gain: volume });
            const source = new AudioBufferSourceNode(context, { buffer: clip });
            source.connect(gain).connect(context.destination);
            source.start();
        },
    };
}
