import { type MessageKey } from "@/i18n";

const GAME_TYPE_NAMES: ReadonlyMap<string, MessageKey> = new Map([
    ["hanchan", "game_type.hanchan"],
    ["tonpusen", "game_type.tonpusen"],
]);

export function gameTypeNameKey(gameType: string): MessageKey | null {
    return GAME_TYPE_NAMES.get(gameType) ?? null;
}

const GAME_TYPE_WINDS: ReadonlyMap<string, string> = new Map([
    ["hanchan", "南"],
    ["tonpusen", "東"],
]);

export function gameTypeWind(gameType: string): string | null {
    return GAME_TYPE_WINDS.get(gameType) ?? null;
}
