/** The settings menu in the board's corner: whether it is open, and its sound, animations and discard slide switches. */
export const SETTINGS_FOCUS_KEY = "settings";

export interface SettingsMenu {
    readonly open: boolean;
    readonly soundOn: boolean;
    readonly animationsOn: boolean;
    readonly discardSlideOn: boolean;
}

/** The menu's own commands: the cog's toggle, a close (Escape, a click outside it) and its switches. */
export type SettingsMenuCommand =
    | "toggle_settings"
    | "close_settings"
    | "toggle_sound"
    | "toggle_animations"
    | "toggle_discard_slide";

/**
 * The menu after one of its own commands, and which setting changed and is to be saved; live and the replay share it,
 * each closing the menu on its own other input.
 */
export function stepSettingsMenu(
    menu: SettingsMenu,
    command: SettingsMenuCommand,
): { readonly menu: SettingsMenu; readonly saved: "sound" | "motion" | null } {
    if (command === "toggle_sound") {
        return { menu: { ...menu, soundOn: !menu.soundOn }, saved: "sound" };
    }
    if (command === "toggle_animations") {
        return { menu: { ...menu, animationsOn: !menu.animationsOn }, saved: "motion" };
    }
    if (command === "toggle_discard_slide") {
        return { menu: { ...menu, discardSlideOn: !menu.discardSlideOn }, saved: "motion" };
    }
    return {
        menu: { ...menu, open: command === "toggle_settings" && !menu.open },
        saved: null,
    };
}
