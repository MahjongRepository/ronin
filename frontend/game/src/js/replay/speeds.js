/** Autoplay's speeds, as the replay's settings store them. */
export const AUTOPLAY_SPEED = Object.freeze({
    SLOW: "slow",
    NORMAL: "normal",
    FAST: "fast",
});

export const DEFAULT_AUTOPLAY_SPEED = AUTOPLAY_SPEED.NORMAL;

/** Autoplay's pause between positions at each speed, the slowest to follow every discard, the fastest to skim. */
export const AUTOPLAY_SPEEDS = Object.freeze({
    [AUTOPLAY_SPEED.SLOW]: 1500,
    [AUTOPLAY_SPEED.NORMAL]: 800,
    [AUTOPLAY_SPEED.FAST]: 400,
});
