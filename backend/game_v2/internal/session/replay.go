package session

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type replayLog struct {
	seed      engine.Seed
	roster    messaging.Roster
	records   []wire.Map
	liveTiles int
}

func (r *replayLog) collect(events []play.Emitted, table func() messaging.Table) error {
	var dealt []play.RoundStarted
	flush := func() {
		if len(dealt) > 0 {
			r.records = append(r.records, messaging.ReplayRoundStartedPayload(dealt))
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

func (r *replayLog) record(event play.Event, table func() messaging.Table) (wire.Map, bool, error) {
	switch e := event.(type) {
	case play.GameStarted:
		return messaging.ReplayGameStartedPayload(e, r.roster, r.seed), true, nil
	case play.Drew:
		r.liveTiles = max(0, r.liveTiles-1)
		return messaging.ReplayDrawPayload(e, r.liveTiles), true, nil
	case play.DrewNotice, play.FuritenChanged, play.RoundStarted:
		return nil, false, nil
	case play.Discarded, play.RiichiDeposited, play.Called, play.PaoAssigned, play.DoraRevealed, play.RoundEnded,
		play.GameEnded:
	}
	record, err := messaging.EventPayload(event, table())
	return record, err == nil, err
}

func (r *replayLog) recordSeatControl(seat tile.Seat, standIn play.Option[wire.SeatControlReason]) {
	record := wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventSeatControl)},
		{Key: wire.KeySeat, Value: wire.Int(seat.Index())},
	}
	if standIn.OK {
		record = append(record,
			wire.Field{Key: wire.KeyAIPlayer, Value: wire.Int(1)},
			wire.Field{Key: wire.KeySeatControlReason, Value: wire.Int(standIn.Value)})
	} else {
		record = append(record, wire.Field{Key: wire.KeyAIPlayer, Value: wire.Int(0)})
	}
	r.records = append(r.records, record)
}

func encodeReplay(records []wire.Map) ([]byte, error) {
	return wire.EncodeReplay(append([]wire.Map{wire.VersionRecord()}, records...))
}
