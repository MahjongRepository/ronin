import {
    AUTO_WIN_SETTING_KEY,
    DEFAULT_AUTO_WIN_SETTING,
    readAutoWinSetting,
} from "@ronin/shared/auto-win-setting";
import {
    DEFAULT_INPUT_SETTING,
    INPUT_SETTING_KEY,
    readInputSetting,
} from "@ronin/shared/input-setting";
import { localStore } from "@ronin/shared/local-store";
import { type Locale } from "@ronin/shared/locale";
import {
    DEFAULT_MOTION_SETTING,
    MOTION_SETTING_KEY,
    readMotionSetting,
} from "@ronin/shared/motion-setting";
import { type MountedView } from "@ronin/shared/router";
import {
    DEFAULT_SOUND_SETTING,
    SOUND_SETTING_KEY,
    readSoundSetting,
} from "@ronin/shared/sound-setting";
import { applyTileLabels } from "@ronin/shared/tile-labels";
import { applyWindScript } from "@ronin/shared/winds";

import { startApiTokenSection } from "@/settings/api-token";
import { renderSettings } from "@/settings/ui";

export interface SettingsViewDeps {
    readonly setLanguage: (locale: Locale) => void;
}

export function mountSettingsView(host: HTMLElement, deps: SettingsViewDeps): MountedView {
    const soundStore = localStore(SOUND_SETTING_KEY, readSoundSetting, DEFAULT_SOUND_SETTING);
    const motionStore = localStore(MOTION_SETTING_KEY, readMotionSetting, DEFAULT_MOTION_SETTING);
    const inputStore = localStore(INPUT_SETTING_KEY, readInputSetting, DEFAULT_INPUT_SETTING);
    const autoWinStore = localStore(
        AUTO_WIN_SETTING_KEY,
        readAutoWinSetting,
        DEFAULT_AUTO_WIN_SETTING,
    );

    function saveAndRender(save: () => void): () => void {
        return () => {
            save();
            render();
        };
    }

    function render(): void {
        const sound = soundStore.load();
        const motion = motionStore.load();
        const input = inputStore.load();
        const autoWin = autoWinStore.load();
        renderSettings(host, {
            accountSection: apiToken.template(),
            animations: {
                on: motion.animations,
                onToggle: saveAndRender(() => motionStore.save({ animations: !motion.animations })),
            },
            input: {
                keyHints: input.keyHints,
                onToggle: saveAndRender(() =>
                    inputStore.save({ ...input, rightClick: !input.rightClick }),
                ),
                onToggleKeyHints: saveAndRender(() =>
                    inputStore.save({ ...input, keyHints: !input.keyHints }),
                ),
                rightClick: input.rightClick,
            },
            keepAutoWin: {
                on: autoWin.keepBetweenRounds,
                onToggle: saveAndRender(() =>
                    autoWinStore.save({ keepBetweenRounds: !autoWin.keepBetweenRounds }),
                ),
            },
            onLanguage: deps.setLanguage,
            onTileLabels: (on) => {
                applyTileLabels(on);
                render();
            },
            onWinds: (script) => {
                applyWindScript(script);
                render();
            },
            sound: {
                on: sound.sound_on,
                onToggle: saveAndRender(() => soundStore.save({ sound_on: !sound.sound_on })),
            },
        });
    }

    const apiToken = startApiTokenSection(render);
    render();
    return { rerender: render, unmount: apiToken.dispose };
}
