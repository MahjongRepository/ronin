import { type StandingsRenderer, startStandingsLoad } from "@/entities/table";
import { type Clock } from "@/shared/clock";
import { type RetryingLoad } from "@/shared/lib";

/** The final standings' load for a storybook page: its retries on the page's timers, with no wait for coming online. */
export function startStorybookStandings(
    setTimer: Clock["setTimer"],
): RetryingLoad<StandingsRenderer> {
    return startStandingsLoad({
        onOnline: () => () => {},
        reportFailure: (error) => console.warn("The final standings failed to load:", error),
        setTimer,
    });
}
