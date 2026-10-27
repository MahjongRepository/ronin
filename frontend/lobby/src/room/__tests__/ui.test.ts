import { afterEach, describe, expect, test, vi } from "vitest";

import { LobbySocket } from "@/lobby-socket";
import { buildActionCallbacks, buildMessageHandlers, handleMessage } from "@/room/handlers";
import { type RoomState, createRoomState } from "@/room/state";
import { renderRoom } from "@/room/ui";

const ROOM_NAME = "Jade Crane";

function seatedState(): RoomState {
    const state = createRoomState();
    state.connectionStatus = "connected";
    state.currentPlayerName = "dev";
    state.isOwner = true;
    state.players = [
        { is_bot: false, is_owner: true, name: "dev", ready: true },
        { is_bot: true, is_owner: false, name: "Tsumogiri Bot 2", ready: true },
    ];
    return state;
}

function mount(state: RoomState): HTMLElement {
    const container = document.createElement("div");
    document.body.append(container);
    renderRoom({
        actions: buildActionCallbacks(state),
        chatMaxLength: 1000,
        container,
        roomName: ROOM_NAME,
        state,
    });
    return container;
}

function chatInput(container: HTMLElement): HTMLInputElement {
    const input = container.querySelector("#chat-input");
    if (!(input instanceof HTMLInputElement)) {
        throw new Error("chat input not rendered");
    }
    return input;
}

function submitChat(container: HTMLElement, text: string): void {
    chatInput(container).value = text;
    container.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
}

describe("renderRoom", () => {
    afterEach(() => {
        document.body.replaceChildren();
    });

    test("shows connecting and a disabled composer before the socket opens", () => {
        const container = mount(createRoomState());

        expect(container.querySelector(".room-header h2")?.textContent).toBe(ROOM_NAME);
        expect(container.querySelector(".connection-status")?.textContent).toBe("Connecting…");
        expect(container.querySelector(".lobby-alert")).toBeNull();
        expect(chatInput(container).disabled).toBe(true);
    });

    test("shows a refused join as a page alert with a way out and no seat controls", () => {
        const state = createRoomState();
        state.connectionStatus = "disconnected";
        state.pageError = { code: "already_in_queue", text: "Cancel the search first." };

        const container = mount(state);

        const alert = container.querySelector(".lobby-alert");
        expect(alert?.textContent).toContain("Cancel the search first.");
        const links = [...(alert?.querySelectorAll("a") ?? [])].map((link) =>
            link.getAttribute("href"),
        );
        expect(links).toEqual(["/matchmaking", "/"]);
        expect(
            container.querySelector("#chat-input, .room-leave-btn, .connection-status"),
        ).toBeNull();
    });

    test("links an already_in_room refusal to the table the server names", () => {
        const state = createRoomState();
        const handlers = buildMessageHandlers(state, vi.fn(), vi.fn());
        handleMessage(handlers, { message: "already_in_room", room_id: "room 1", type: "error" });

        const container = mount(state);

        const links = [...container.querySelectorAll(".lobby-alert a")].map((link) => [
            link.getAttribute("href"),
            link.textContent,
        ]);
        expect(links).toEqual([
            ["/rooms/room%201", "Go to your table"],
            ["/", "Back to lobby"],
        ]);
    });

    test("warns when a seated player's connection drops and disables sending", () => {
        const state = seatedState();
        state.connectionStatus = "error";

        const container = mount(state);

        expect(container.querySelector(".lobby-alert.warning")?.textContent).toContain("Reload");
        expect(container.querySelector(".connection-status.status-error")).not.toBeNull();
        expect(chatInput(container).disabled).toBe(true);
        expect(container.querySelector<HTMLButtonElement>(".room-start-btn")?.disabled).toBe(true);
    });

    test("keeps the chat draft when the send fails and clears it once sent", () => {
        const state = seatedState();
        state.socket = new LobbySocket(vi.fn(), vi.fn());
        const send = vi.spyOn(state.socket, "send").mockReturnValue(false);
        const container = mount(state);

        submitChat(container, "  hello  ");
        expect(chatInput(container).value).toBe("  hello  ");

        send.mockReturnValue(true);
        submitChat(container, "  hello  ");
        expect(send).toHaveBeenLastCalledWith({ text: "hello", type: "chat" });
        expect(chatInput(container).value).toBe("");
    });

    test("does not submit the chat on the Enter that confirms an IME composition", () => {
        const container = mount(seatedState());
        const input = chatInput(container);

        const composing = new KeyboardEvent("keydown", {
            cancelable: true,
            isComposing: true,
            key: "Enter",
        });
        input.dispatchEvent(composing);
        const plain = new KeyboardEvent("keydown", { cancelable: true, key: "Enter" });
        input.dispatchEvent(plain);

        expect(composing.defaultPrevented).toBe(true);
        expect(plain.defaultPrevented).toBe(false);
    });

    test("explains why the host cannot start yet", () => {
        const state = seatedState();
        state.players.push({ is_bot: false, is_owner: false, name: "dev2", ready: false });

        const container = mount(state);

        const start = container.querySelector<HTMLButtonElement>(".room-start-btn");
        expect(start?.disabled).toBe(true);
        expect(
            container.querySelector(`#${start?.getAttribute("aria-describedby")}`)?.textContent,
        ).toBe("Waiting for dev2 to get ready.");
    });

    test("marks your own seat and shows the host as the host rather than ready", () => {
        const state = seatedState();
        state.players.push({ is_bot: false, is_owner: false, name: "dev2", ready: true });

        const container = mount(state);

        const rows = [...container.querySelectorAll(".room-player-item")].map((row) => ({
            badges: [...row.querySelectorAll(".room-player-badge")].map(
                (badge) => badge.textContent,
            ),
            me: row.classList.contains("me"),
            status: row.querySelector(".room-player-status")?.getAttribute("aria-label"),
        }));
        expect(rows).toEqual([
            { badges: ["You", "Host"], me: true, status: "Host" },
            { badges: [], me: false, status: "Open seat" },
            { badges: [], me: false, status: "Ready" },
        ]);
    });

    test("drops the ready hint while a guest's connection is lost", () => {
        const state = seatedState();
        state.isOwner = false;
        state.players = [{ is_bot: false, is_owner: false, name: "dev", ready: false }];
        state.connectionStatus = "disconnected";

        const container = mount(state);

        expect(container.querySelector<HTMLButtonElement>(".room-ready-btn")?.disabled).toBe(true);
        expect(container.querySelector(".room-action-hint")).toBeNull();
    });
});
