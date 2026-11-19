import { t } from "@/i18n";

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;

export function formatDuration(durationSeconds: number): string {
    const seconds = Math.max(Math.trunc(durationSeconds), 0);
    if (seconds >= SECONDS_PER_HOUR) {
        return t("duration.hours", {
            hours: Math.floor(seconds / SECONDS_PER_HOUR),
            minutes: Math.floor((seconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE),
        });
    }
    if (seconds >= SECONDS_PER_MINUTE) {
        return t("duration.minutes", {
            minutes: Math.floor(seconds / SECONDS_PER_MINUTE),
            seconds: seconds % SECONDS_PER_MINUTE,
        });
    }
    return t("duration.seconds", { seconds });
}
