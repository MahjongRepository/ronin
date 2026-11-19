import { pageLocale } from "./locale";

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
    return new Intl.NumberFormat(pageLocale(), options).format(value);
}

export function formatList(items: readonly string[]): string {
    return new Intl.ListFormat(pageLocale(), { type: "conjunction" }).format(items);
}

export function formatTime(date: Date): string {
    return date.toLocaleTimeString(pageLocale(), { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(date: Date): string {
    return new Intl.DateTimeFormat(pageLocale(), {
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        month: "short",
    }).format(date);
}
