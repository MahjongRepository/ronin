import { type StandingsRenderer } from "@/entities/table";
import { renderStandings } from "@/entities/table/ui/standings";
import { type LoadStatus, type RetryingLoad } from "@/shared/lib";

/** The final standings' load, ready from the start unless asked otherwise, moved by hand; it holds the real renderer. */
export class FakeStandingsLoad implements RetryingLoad<StandingsRenderer> {
    stopped = false;
    private current: LoadStatus;
    private readonly listeners = new Set<(status: LoadStatus) => void>();

    constructor(status: LoadStatus = "ready") {
        this.current = status;
    }

    status = (): LoadStatus => this.current;

    value = (): StandingsRenderer | null => (this.current === "ready" ? renderStandings : null);

    subscribe = (listener: (status: LoadStatus) => void): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    stop = (): void => {
        this.stopped = true;
        this.listeners.clear();
    };

    moveTo(status: LoadStatus): void {
        this.current = status;
        for (const listener of this.listeners) {
            listener(status);
        }
    }
}
