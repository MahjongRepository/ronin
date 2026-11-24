import { localStore } from "./local-store";
import { applyTileLabels, restoreTileLabels } from "./tile-labels";

export type BoardAppearanceSetting = "compassDora" | "tileLabels";
export type SetBoardAppearance = (setting: BoardAppearanceSetting, on: boolean) => void;

export const COMPASS_DORA_KEY = "ronin.v2.compass-dora";
const compassDoraStore = localStore(COMPASS_DORA_KEY, (stored) => stored === true, false);

export function pageCompassDora(): boolean {
    return document.documentElement.hasAttribute("data-compass-dora");
}

export function applyBoardAppearance(setting: BoardAppearanceSetting, on: boolean): void {
    if (setting === "tileLabels") {
        applyTileLabels(on);
        return;
    }
    document.documentElement.toggleAttribute("data-compass-dora", on);
    compassDoraStore.save(on);
}

export function restoreBoardAppearance(): void {
    restoreTileLabels();
    document.documentElement.toggleAttribute("data-compass-dora", compassDoraStore.load());
}
