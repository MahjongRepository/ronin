import { type TemplateResult, html } from "lit-html";

import { GameMenu, connectionDisplay } from "@/entities/client";
import { type SessionStatusDisplay } from "@/entities/session";
import { type MessageKey, t } from "@/shared/i18n";
import { CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";
import { storybookNav } from "@/views/storybook-nav";

interface ConnectionStory {
    readonly name: string;
    readonly tone: ConnectionStatus;
    readonly label: MessageKey;
    readonly word: MessageKey | null;
    readonly roundTripMs: number | null;
}

const CONNECTION_STORIES: readonly ConnectionStory[] = [
    {
        label: "game.status.connected",
        name: "connected",
        roundTripMs: 85,
        tone: CONNECTION_STATUS.CONNECTED,
        word: null,
    },
    {
        label: "game.status.connected",
        name: "slow",
        roundTripMs: 520,
        tone: CONNECTION_STATUS.CONNECTED,
        word: null,
    },
    {
        label: "game.status.connected",
        name: "unmeasured",
        roundTripMs: null,
        tone: CONNECTION_STATUS.CONNECTED,
        word: null,
    },
    {
        label: "game.status.connecting",
        name: "connecting",
        roundTripMs: null,
        tone: CONNECTION_STATUS.CONNECTING,
        word: "game.status.connecting",
    },
    {
        label: "game.status.reconnecting",
        name: "offline",
        roundTripMs: null,
        tone: CONNECTION_STATUS.DISCONNECTED,
        word: "game.status.word.offline",
    },
    {
        label: "game.status.disconnected",
        name: "error",
        roundTripMs: null,
        tone: CONNECTION_STATUS.ERROR,
        word: "game.status.word.error",
    },
    {
        label: "game.status.game_over",
        name: "ended",
        roundTripMs: null,
        tone: CONNECTION_STATUS.DISCONNECTED,
        word: "game.status.word.ended",
    },
];

function ignore(): void {}

/** A connection state as the live game shows it: the cog's mark, and the open settings' connection row. */
function ConnectionStoryView(story: ConnectionStory): TemplateResult {
    const status: SessionStatusDisplay = {
        label: t(story.label),
        tone: story.tone,
        word: story.word === null ? "" : t(story.word),
    };
    const display = connectionDisplay(status, story.roundTripMs);
    return html`<div class="storybook-connection">
        <small>${story.name}</small>
        ${GameMenu({
            alert: display.cogAlert,
            animationsOn: true,
            backdrop: false,
            onClose: ignore,
            onLanguage: ignore,
            onTileLabels: ignore,
            onToggleAnimations: ignore,
            onToggleOpen: ignore,
            onToggleSound: ignore,
            onWinds: ignore,
            open: true,
            roundTrip: display.roundTrip,
            soundOn: true,
            status: display.status,
        })}
    </div>`;
}

function storybookSystemView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/system")}

            <section>
                <h2>Connection status</h2>
                <div class="storybook-connections">${CONNECTION_STORIES.map(ConnectionStoryView)}</div>
            </section>
        </div>
    `;
}

export { storybookSystemView };
