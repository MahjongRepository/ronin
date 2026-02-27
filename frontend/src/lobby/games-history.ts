export function initGamesCopyButtons(): void {
    document.querySelectorAll<HTMLButtonElement>(".games-copy-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const { gameId } = btn.dataset;
            if (!gameId) {
                return;
            }

            navigator.clipboard.writeText(gameId).then(() => {
                btn.classList.add("copied");
                setTimeout(() => btn.classList.remove("copied"), 1500);
            });
        });
    });
}
