import { isMessageKey, reportI18nError, t } from "@/shared/i18n";

export function yakuName(yakuId: number): string {
    const key = `yaku.${yakuId}`;
    if (isMessageKey(key)) {
        return t(key);
    }
    reportI18nError(key, "unknown yaku id");
    return t("yaku.unknown", { id: String(yakuId) });
}
