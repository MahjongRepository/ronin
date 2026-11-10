import "@/styles/storybook-page.scss";
import { html, render } from "lit-html";

import { type SoundCue } from "@/entities/client";
import { storybookNav } from "@/views/storybook-nav";

interface SoundGroup {
    readonly title: string;
    readonly description: string;
    readonly sounds: readonly { readonly cue: SoundCue; readonly label: string }[];
}

const SOUND_GROUPS = [
    {
        description:
            "A tile discard, a new call, riichi or win opportunity, and the final seconds of a decision.",
        sounds: [
            { cue: "discard", label: "Tile clack" },
            { cue: "decision", label: "Call, riichi or win prompt · Radar reply + tile" },
            { cue: "beep", label: "Soft countdown" },
        ],
        title: "Game cues",
    },
    {
        description: "Voices for declared calls and riichi.",
        sounds: [
            { cue: "chi", label: "Chi" },
            { cue: "pon", label: "Pon" },
            { cue: "kan", label: "Kan" },
            { cue: "riichi", label: "Riichi" },
        ],
        title: "Calls",
    },
    {
        description: "Winning declarations and the additional yakuman announcement.",
        sounds: [
            { cue: "ron", label: "Ron" },
            { cue: "tsumo", label: "Tsumo" },
            { cue: "yakuman", label: "Yakuman" },
        ],
        title: "Wins",
    },
] as const satisfies readonly SoundGroup[];

interface SoundPreviewDeps {
    readonly sounds: Readonly<Record<SoundCue, { readonly volume: number }>>;
    readonly play: (cue: SoundCue) => void;
}

export function mountStorybookSounds(
    host: HTMLElement,
    { sounds, play }: SoundPreviewDeps,
): () => void {
    render(
        html`
        <main class="storybook">
            ${storybookNav("/play/storybook/sounds")}
            <p>Tap a sound to hear it at its in-game volume. Repeated taps overlap just as they do in play.</p>
            ${SOUND_GROUPS.map(
                (group) => html`
                <section>
                    <h2>${group.title}</h2>
                    <p>${group.description}</p>
                    <div class="storybook-tile-row">
                        ${group.sounds.map(
                            ({ cue, label }) => html`
                            <button type="button" @click=${() => play(cue)}>
                                ${label} · ${Math.round(sounds[cue].volume * 100)}%
                            </button>
                        `,
                        )}
                    </div>
                </section>
                `,
            )}
        </main>
    `,
        host,
    );
    return () => render(null, host);
}
