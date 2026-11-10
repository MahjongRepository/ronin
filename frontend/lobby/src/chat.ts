import { type TemplateResult, html, nothing } from "lit-html";

import { t } from "@/i18n";

const IME_PROCESS_KEY_CODE = 229;
const LOG_TYPE_SYSTEM = "system";
const CHAT_LOG_ID = "room-chat-messages";

interface ChatEntry {
    sender: string;
    text: string;
    timestamp: string;
}

interface ChatComposer {
    chatMaxLength: number;
    enabled: boolean;
    send: (text: string) => boolean;
}

function chatEntryTemplate(entry: ChatEntry): TemplateResult {
    const system = entry.sender === LOG_TYPE_SYSTEM;
    return html`
        <div class="room-chat-entry ${system ? "system" : ""}">
            <span class="room-chat-time">${entry.timestamp}</span>
            ${system ? nothing : html`<span class="room-chat-sender">${entry.sender}</span>`}
            <span class="room-chat-text">${entry.text}</span>
        </div>
    `;
}

function chatLogTemplate(entries: readonly ChatEntry[]): TemplateResult {
    return html`
        <div class="room-chat-messages" id=${CHAT_LOG_ID} role="log" aria-live="polite">
            ${entries.map(chatEntryTemplate)}
        </div>
    `;
}

function blockImeEnter(event: KeyboardEvent): void {
    const composing = event.isComposing || event.keyCode === IME_PROCESS_KEY_CODE;
    if (event.key === "Enter" && composing) {
        event.preventDefault();
    }
}

function chatComposerTemplate({ chatMaxLength, enabled, send }: ChatComposer): TemplateResult {
    function handleSubmit(event: SubmitEvent): void {
        event.preventDefault();
        const form = event.currentTarget;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        const input = form.elements.namedItem("text");
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        if (send(input.value)) {
            input.value = "";
        }
    }

    return html`
        <form class="room-chat-input" role="group" @submit=${handleSubmit}>
            <input type="text"
                   id="chat-input"
                   name="text"
                   aria-label=${t("chat.label")}
                   autocomplete="off"
                   maxlength=${chatMaxLength}
                   placeholder=${t("chat.placeholder")}
                   ?disabled=${!enabled}
                   @keydown=${blockImeEnter} />
            <button type="submit" class="outline" ?disabled=${!enabled}>${t("chat.send")}</button>
        </form>
    `;
}

function scrollChatToLatest(container: HTMLElement, count: number): void {
    const log = container.querySelector<HTMLElement>(`#${CHAT_LOG_ID}`);
    if (!log || log.dataset.count === String(count)) {
        return;
    }
    log.dataset.count = String(count);
    log.scrollTop = log.scrollHeight;
}

export { LOG_TYPE_SYSTEM, chatComposerTemplate, chatLogTemplate, scrollChatToLatest };
export type { ChatEntry };
