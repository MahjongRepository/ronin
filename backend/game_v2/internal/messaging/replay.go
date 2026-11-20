package messaging

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// ReplayLog collects a game's replay records as the server saves them: the game start with its
// seed, each round's deal as one record of every hand, each draw once with the live tiles left
// after it, every other event the engine emits but the draw notices and furiten changes, and the
// seat control records added between them. The version record is not among them.
type ReplayLog struct {
	seed      engine.Seed
	roster    Roster
	records   []wire.Map
	liveTiles int
}

// NewReplayLog returns an empty log of the game seed starts, played by roster.
func NewReplayLog(seed engine.Seed, roster Roster) *ReplayLog {
	return &ReplayLog{seed: seed, roster: roster}
}

// Collect appends the records of one engine call's events. table gives the Table after the call,
// and is asked for only when a record names what it holds. The error is EventPayload's.
func (r *ReplayLog) Collect(events []play.Emitted, table func() Table) error {
	var dealt []play.RoundStarted
	flush := func() {
		if len(dealt) > 0 {
			r.records = append(r.records, ReplayRoundStartedPayload(dealt))
			r.liveTiles = dealt[0].LiveTiles
			dealt = nil
		}
	}

	for _, emitted := range events {
		if e, isDeal := emitted.Event.(play.RoundStarted); isDeal {
			dealt = append(dealt, e)
			continue
		}
		flush()

		record, kept, err := r.record(emitted.Event, table)
		if err != nil {
			return err
		}
		if kept {
			r.records = append(r.records, record)
		}
	}
	flush()
	return nil
}

// AddSeatControl appends the seat control record of a handover: to an AI player for reason, or
// back to the seat's participant when reason is absent.
func (r *ReplayLog) AddSeatControl(seat tile.Seat, reason play.Option[wire.SeatControlReason]) {
	r.records = append(r.records, ReplaySeatControlPayload(seat, reason))
}

// Records returns the records collected so far, in their order.
func (r *ReplayLog) Records() []wire.Map {
	return slices.Clone(r.records)
}

// EncodeReplayRecords encodes records, as Records returns them, into a replay's content: the
// version record first, then records. The error is wire.EncodeReplay's.
func EncodeReplayRecords(records []wire.Map) ([]byte, error) {
	return wire.EncodeReplay(append([]wire.Map{wire.VersionRecord()}, records...))
}

func (r *ReplayLog) record(event play.Event, table func() Table) (wire.Map, bool, error) {
	switch e := event.(type) {
	case play.GameStarted:
		return ReplayGameStartedPayload(e, r.roster, r.seed), true, nil
	case play.Drew:
		r.liveTiles = max(0, r.liveTiles-1)
		return ReplayDrawPayload(e, r.liveTiles), true, nil
	case play.DrewNotice, play.FuritenChanged, play.RoundStarted:
		return nil, false, nil
	case play.Discarded, play.RiichiDeposited, play.Called, play.PaoAssigned, play.DoraRevealed, play.RoundEnded,
		play.GameEnded:
	}
	record, err := EventPayload(event, table)
	return record, err == nil, err
}
