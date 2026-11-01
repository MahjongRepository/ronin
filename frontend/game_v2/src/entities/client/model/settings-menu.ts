/** The settings menu in the board's corner: whether it is open, and its sound switch. */
export interface SettingsMenu {
    readonly open: boolean;
    readonly soundOn: boolean;
}

/** The menu's own commands: the cog's toggle, a close (Escape, the backdrop) and the sound switch. */
export type SettingsMenuCommand = "toggle_settings" | "close_settings" | "toggle_sound";

/**
 * The menu after one of its own commands, and whether the sound setting changed and is to be saved; live and the
 * replay share it, each closing the menu on its own other input.
 */
export function stepSettingsMenu(
    menu: SettingsMenu,
    command: SettingsMenuCommand,
): { readonly menu: SettingsMenu; readonly saveSound: boolean } {
    if (command === "toggle_sound") {
        return { menu: { ...menu, soundOn: !menu.soundOn }, saveSound: true };
    }
    return {
        menu: { ...menu, open: command === "toggle_settings" && !menu.open },
        saveSound: false,
    };
}
