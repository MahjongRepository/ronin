const HTTP_NOT_FOUND = 404;

async function fetchReplayText(gameId) {
    let response;
    try {
        response = await fetch(`/api/replays/${encodeURIComponent(gameId)}`);
    } catch {
        return { error: "Failed to load replay" };
    }
    if (response.status === HTTP_NOT_FOUND) {
        return { error: "Replay not found" };
    }
    if (!response.ok) {
        return { error: `Failed to load replay (${response.status})` };
    }
    return { text: await response.text() };
}

export async function showReplay(root, gameId) {
    const heading = document.createElement("h1");
    heading.textContent = `Replay ${gameId}`;
    const status = document.createElement("p");
    status.className = "replay-status";
    status.textContent = "Loading replay...";
    const content = document.createElement("pre");
    content.className = "replay-content";
    root.replaceChildren(heading, status, content);

    const result = await fetchReplayText(gameId);
    if (result.error) {
        status.textContent = result.error;
        return;
    }
    status.remove();
    content.textContent = result.text;
}
