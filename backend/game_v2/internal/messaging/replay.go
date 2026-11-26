package messaging

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type ReplayLog struct {
	seed      engine.Seed
	roster    Roster
	records   []wire.Map
	liveTiles int
}

func NewReplayLog(seed engine.Seed, roster Roster) *ReplayLog {
	return &ReplayLog{seed: seed, roster: roster}
}

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

func (r *ReplayLog) AddSeatControl(seat tile.Seat, reason play.Option[wire.SeatControlReason]) {
	r.records = append(r.records, ReplaySeatControlPayload(seat, reason))
}

func (r *ReplayLog) Records() []wire.Map {
	return slices.Clone(r.records)
}

func (r *ReplayLog) RecordsSince(n int) []wire.Map {
	return slices.Clone(r.records[n:])
}

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
