export function initGamesCopyLinkButtons(): void {
    document.querySelectorAll<HTMLElement>(".games-card[data-replay-url]").forEach((card) => {
        card.addEventListener("click", () => {
            const { replayUrl } = card.dataset;
            if (replayUrl) {
                window.location.href = replayUrl;
            }
        });
    });

    document.querySelectorAll<HTMLButtonElement>(".games-copy-btn").forEach((btn) => {
        btn.addEventListener("click", (event) => {
            event.stopPropagation();

            const { replayUrl } = btn.dataset;
            if (!replayUrl) {
                return;
            }

            const fullUrl = window.location.origin + replayUrl;
            navigator.clipboard.writeText(fullUrl).then(
                () => {
                    btn.classList.add("copied");
                    setTimeout(() => btn.classList.remove("copied"), 1500);
                },
                () => {},
            );
        });
    });
}
