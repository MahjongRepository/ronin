import $ from "jquery";

const offsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetWidth");
Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 1 });
$.support.reliableTrDimensions();
Object.defineProperty(HTMLElement.prototype, "offsetWidth", offsetWidth);
