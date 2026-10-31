export type { EndReason, SessionEffect, SessionInput, SessionState } from "./model/types";
export {
    awaitsSnapshot,
    canRequestResync,
    failSession,
    hasLostSeat,
    hasSocket,
    holdsSeat,
    sessionDeadline,
    startSession,
    stepSession,
    takesMessages,
} from "./model/transition";
export type { SessionStatusDisplay } from "./lib/session-status";
export { describePlayerSessionStatus, describeSessionStatus } from "./lib/session-status";
