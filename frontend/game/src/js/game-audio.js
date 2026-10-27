/**
 * Wrap a `Majiang.UI.audio` loader so that a sound the browser refuses to play before the page's first user gesture (a
 * page reloaded mid-game, a replay's autoplay) is skipped instead of rejecting unhandled. Any other failure still
 * rejects.
 */
export function withoutBlockedPlayback(loadAudio) {
    return (name) => {
        const sound = loadAudio(name);
        const play = sound.play.bind(sound);
        sound.play = () =>
            play().catch((error) => {
                if (error.name !== "NotAllowedError") {
                    throw error;
                }
            });
        return sound;
    };
}
