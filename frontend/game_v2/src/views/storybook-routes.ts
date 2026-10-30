import "@/styles/storybook-page.scss";
import { staticMount } from "@/router";
import { storybookView } from "@/views/storybook";
import { storybookDiscardsView } from "@/views/storybook-discards";
import { storybookHandView } from "@/views/storybook-hand";
import { storybookMeldsView } from "@/views/storybook-melds";

export { mountStorybookBoard } from "@/views/storybook-board";
export { mountStorybookDecisions } from "@/views/storybook-decisions";
export { mountStorybookReplay } from "@/views/storybook-replay";
export { mountStorybookRotate } from "@/views/storybook-rotate";

export const mountStorybookIndex = staticMount(storybookView);
export const mountStorybookDiscards = staticMount(storybookDiscardsView);
export const mountStorybookHand = staticMount(storybookHandView);
export const mountStorybookMelds = staticMount(storybookMeldsView);
