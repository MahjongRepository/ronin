import { beforeEach, describe, expect, test, vi } from "vitest";

let capturedMessageHandler: ((message: Record<string, unknown>) => void) | null = null;
let capturedStatusHandler: ((status: string) => void) | null = null;

const mockConnect = vi.fn();

vi.mock("@/lobby-socket", () => ({
    LobbySocket: class MockLobbySocket {
        constructor(
            onMessage: (message: Record<string, unknown>) => void,
            onStatusChange: (status: string) => void,
        ) {
            capturedMessageHandler = onMessage;
            capturedStatusHandler = onStatusChange;
        }

        connect = mockConnect;
        disconnect = vi.fn();
    },
}));

const { initMatchmakingPage } = await import("@/matchmaking");

const WS_URL = "ws://lobby/ws/matchmaking";

function renderPage(): HTMLElement {
    document.body.innerHTML = `
        <div id="matchmaking-app">
            <p class="matchmaking-status">Connecting...</p>
            <p class="matchmaking-queue-count"></p>
            <button type="button" class="matchmaking-retry" hidden>Find match again</button>
        </div>`;
    initMatchmakingPage(WS_URL);
    return query(document.body, "#matchmaking-app");
}

function query<ElementType extends HTMLElement = HTMLElement>(
    container: HTMLElement,
    selector: string,
): ElementType {
    const element = container.querySelector<ElementType>(selector);
    if (!element) {
        throw new Error(`missing ${selector}`);
    }
    return element;
}

describe("initMatchmakingPage", () => {
    beforeEach(() => {
        mockConnect.mockClear();
    });

    test("keeps the match_failed error and offers a retry despite late queue messages and the close", () => {
        const container = renderPage();
        capturedMessageHandler?.({ queue_size: 4, type: "queue_update" });

        capturedMessageHandler?.({ message: "match_failed", type: "error" });
        capturedMessageHandler?.({ position: 3, queue_size: 3, type: "queue_joined" });
        capturedMessageHandler?.({ queue_size: 2, type: "queue_update" });
        capturedStatusHandler?.("disconnected");

        expect(query(container, ".matchmaking-status").textContent).toBe(
            "The match could not be started.",
        );
        expect(query(container, ".matchmaking-queue-count").textContent).toBe("");
        expect(query<HTMLButtonElement>(container, ".matchmaking-retry").hidden).toBe(false);
    });

    test("reconnects and hides the retry when Find match again is clicked", () => {
        const container = renderPage();
        capturedMessageHandler?.({ message: "match_failed", type: "error" });
        capturedStatusHandler?.("disconnected");
        const retry = query<HTMLButtonElement>(container, ".matchmaking-retry");

        retry.click();
        capturedStatusHandler?.("connected");

        expect(mockConnect).toHaveBeenCalledTimes(2);
        expect(mockConnect).toHaveBeenLastCalledWith(WS_URL);
        expect(retry.hidden).toBe(true);
        expect(query(container, ".matchmaking-status").textContent).toBe(
            "Connected, waiting for players...",
        );
    });

    test.each([
        [
            "already_in_game",
            "You are already playing a game. Finish it before joining another.",
            false,
        ],
        ["already_in_queue", "You are already searching for a match. Leave the queue first.", true],
        ["already_in_room", "You are already seated in a room. Leave it first.", true],
    ])(
        "keeps the %s rejection as a sentence, offering a retry only after a game",
        (code, sentence, retryHidden) => {
            const container = renderPage();

            capturedMessageHandler?.({ message: code, type: "error" });
            capturedStatusHandler?.("disconnected");

            expect(query(container, ".matchmaking-status").textContent).toBe(sentence);
            expect(query<HTMLButtonElement>(container, ".matchmaking-retry").hidden).toBe(
                retryHidden,
            );
        },
    );

    test("shows a disconnect after a non-terminal error", () => {
        const container = renderPage();

        capturedMessageHandler?.({ message: "Invalid message format", type: "error" });
        capturedStatusHandler?.("disconnected");

        expect(query(container, ".matchmaking-status").textContent).toBe(
            "Disconnected from server",
        );
    });
});
