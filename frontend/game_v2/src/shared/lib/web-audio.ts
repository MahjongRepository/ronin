import { type SoundOutput } from "./sound-player";

/** The rate files are decoded at; a clip plays resampled to its context's own. */
const DECODE_SAMPLE_RATE = 44_100;

/** A Web Audio output with the unlock iOS Safari needs: a context made and resumed inside a user gesture's handler. */
export interface WebAudioOutput extends SoundOutput<AudioBuffer> {
    /**
     * Make the playing context and resume it, called synchronously inside a user gesture's handler; resolves whether it
     * now runs. Before the page's first user gesture (`hasBeenActive`) it makes nothing and resolves false.
     */
    readonly unlock: () => Promise<boolean>;
}

/**
 * The browser's Web Audio as a player's output: each file fetched and decoded once, each play a source of its own.
 * Files decode offline, and the playing context is made only after the page's first user gesture (`hasBeenActive`),
 * by `unlock` inside a gesture or else at the first play, so no context waits suspended for one and no plays pile up
 * to burst out at it.
 */
export function webAudioOutput(hasBeenActive: () => boolean): WebAudioOutput {
    const decoder = new OfflineAudioContext(1, 1, DECODE_SAMPLE_RATE);
    let context: AudioContext | null = null;
    async function running(): Promise<AudioContext> {
        if (!hasBeenActive()) {
            throw new DOMException("No user gesture yet", "NotAllowedError");
        }
        context ??= new AudioContext();
        if (context.state !== "running") {
            await context.resume();
        }
        return context;
    }
    return {
        load: async (source) => {
            if (source.kind === "generated") {
                const buffer = decoder.createBuffer(1, source.samples.length, source.sampleRate);
                buffer.copyToChannel(source.samples, 0);
                return buffer;
            }
            const { url } = source;
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`The sound file ${url} answered ${response.status}`);
            }
            return decoder.decodeAudioData(await response.arrayBuffer());
        },
        start: async (clip, volume) => {
            const playing = await running();
            const gain = new GainNode(playing, { gain: volume });
            const source = new AudioBufferSourceNode(playing, { buffer: clip });
            source.connect(gain).connect(playing.destination);
            source.start();
        },
        unlock: async () => {
            if (!hasBeenActive()) {
                return false;
            }
            const playing = await running();
            return playing.state === "running";
        },
    };
}
