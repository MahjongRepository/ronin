import { type SoundSamples } from "./sound-player";

const SAMPLE_RATE = 44_100;

export function synthesizeDecision(): SoundSamples {
    return synthesizeChime(
        [
            { decay: 0.06, delay: 0, frequency: 660, gain: 0.45 },
            { decay: 0.06, delay: 0, frequency: 990, gain: 0.15 },
        ],
        0.18,
    );
}

interface ChimeTone {
    readonly frequency: number;
    readonly gain: number;
    readonly decay: number;
    readonly delay: number;
}

function synthesizeChime(tones: readonly ChimeTone[], duration: number): SoundSamples {
    const samples = new Float32Array(Math.round(SAMPLE_RATE * duration));
    for (let i = 0; i < samples.length; i++) {
        const release = Math.min((samples.length - 1 - i) / (SAMPLE_RATE * 0.03), 1);
        for (const tone of tones) {
            samples[i] += release * chimeSample(tone, i / SAMPLE_RATE - tone.delay);
        }
    }
    return { sampleRate: SAMPLE_RATE, samples };
}

function chimeSample(tone: ChimeTone, time: number): number {
    if (time < 0) {
        return 0;
    }
    const attack = Math.min(time / 0.012, 1);
    return (
        attack *
        Math.exp(-time / tone.decay) *
        tone.gain *
        Math.sin(2 * Math.PI * tone.frequency * time)
    );
}
