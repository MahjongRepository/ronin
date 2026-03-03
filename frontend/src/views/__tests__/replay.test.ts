import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

let capturedOnToggle: (() => void) | null = null;

vi.mock("lit-html", () => ({
    html: (..._args: unknown[]) => ({ _brand: "template" }),
    render: vi.fn(),
}));

vi.mock("@/entities/table", () => ({
    GameBoard: vi.fn(() => ({ _brand: "template" })),
    GameEndDisplay: vi.fn(() => ({ _brand: "template" })),
    RoundEndDisplay: vi.fn(() => ({ _brand: "template" })),
    RoundSelector: vi.fn((props: { onToggle: () => void }) => {
        capturedOnToggle = props.onToggle;
        return { _brand: "template" };
    }),
    TurnSelector: vi.fn(() => ({ _brand: "template" })),
    buildActionSteps: vi.fn().mockReturnValue([]),
    buildNavigationIndex: vi.fn().mockReturnValue({ rounds: [] }),
    buildTimeline: vi.fn().mockReturnValue([]),
    formatRoundName: vi.fn().mockReturnValue("East 1"),
    roundForStep: vi.fn().mockReturnValue(undefined),
    tableStateToDisplayState: vi.fn(() => null),
    turnsForStep: vi.fn().mockReturnValue([]),
}));

const { render: litRender } = await import("lit-html");
const { cleanupReplayView, handleClickOutside, replayView } = await import("@/views/replay");

const mockRender = litRender as ReturnType<typeof vi.fn>;

function setupContainer(): void {
    const container = document.createElement("div");
    container.id = "replay-state-container";
    document.body.appendChild(container);
}

function makeClickEvent(target: Element): MouseEvent {
    const event = new MouseEvent("click", { bubbles: true });
    Object.defineProperty(event, "target", { value: target });
    return event;
}

async function flushAsyncChain(): Promise<void> {
    // Drain microtask queue multiple levels deep to let chained awaits settle.
    // Each then-callback pushes the resolution one level deeper.
    await Promise.resolve()
        .then(() => Promise.resolve())
        .then(() => Promise.resolve())
        .then(() => Promise.resolve())
        .then(() => Promise.resolve())
        .then(() => Promise.resolve());
}

/** Load the replay view and wait for async initialization to complete. */
async function initReplayView(): Promise<void> {
    setupContainer();
    globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(""),
    }) as unknown as typeof fetch;
    replayView("test-game");
    vi.runAllTimers();
    await flushAsyncChain();
}

/** Initialize replay view and open the round dropdown via the captured toggle callback. */
async function initWithOpenDropdown(): Promise<void> {
    await initReplayView();
    expect(capturedOnToggle).not.toBeNull();
    capturedOnToggle!();
}

beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = "";
    capturedOnToggle = null;
    mockRender.mockClear();
});

afterEach(() => {
    cleanupReplayView();
    vi.useRealTimers();
});

describe("handleClickOutside", () => {
    test("no-op when no dropdown is open", async () => {
        await initReplayView();
        const callsBefore = mockRender.mock.calls.length;

        handleClickOutside(makeClickEvent(document.body));

        expect(mockRender.mock.calls.length).toBe(callsBefore);
    });

    test("no-op when click is inside .dropdown-select", async () => {
        await initWithOpenDropdown();
        const callsBefore = mockRender.mock.calls.length;

        const dropdown = document.createElement("div");
        dropdown.className = "dropdown-select";
        document.body.appendChild(dropdown);
        const inner = document.createElement("button");
        dropdown.appendChild(inner);

        handleClickOutside(makeClickEvent(inner));

        expect(mockRender.mock.calls.length).toBe(callsBefore);
    });

    test("closes dropdown when click is outside any .dropdown-select", async () => {
        await initWithOpenDropdown();
        const callsBefore = mockRender.mock.calls.length;

        const outside = document.createElement("div");
        document.body.appendChild(outside);

        handleClickOutside(makeClickEvent(outside));

        // updateStateDisplay was called, which invoked render
        expect(mockRender.mock.calls.length).toBeGreaterThan(callsBefore);

        // Calling again is a no-op since dropdown is now closed
        const callsAfterClose = mockRender.mock.calls.length;
        handleClickOutside(makeClickEvent(outside));
        expect(mockRender.mock.calls.length).toBe(callsAfterClose);
    });
});
