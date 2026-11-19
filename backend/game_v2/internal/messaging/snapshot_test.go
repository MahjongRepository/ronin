package messaging_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func tenpaiSeatOneWall(t *testing.T) [tile.TileIDCount]tile.TileID {
	t.Helper()
	tenpai := slices.Concat(copies(t, 1, "123456789m"), copies(t, 1, "11p"), copies(t, 1, "45s"))
	return fixedWall(t, [tile.SeatCount][]tile.TileID{junk(t, 0), tenpai, junk(t, 2), junk(t, 3)}, copies(t, 0, "9999p"))
}

func snapshot(t *testing.T, g engine.Game, s tile.Seat) wire.Map {
	t.Helper()
	m, err := messaging.ReconnectionPayload(g.View(s).Record, testRoster(), [tile.SeatCount]play.Option[wire.SeatControlReason]{})
	if err != nil {
		t.Fatalf("ReconnectionPayload error = %v", err)
	}
	_, err = wire.Encode(m)
	if err != nil {
		t.Fatalf("Encode(snapshot) error = %v", err)
	}
	return m
}

func seatScores(t *testing.T, m wire.Map) []int {
	t.Helper()
	var got []int
	for _, state := range field(t, m, wire.KeyPlayerStates).(wire.Array) {
		got = append(got, int(field(t, state.(wire.Map), wire.KeyScore).(wire.Int)))
	}
	return got
}

func riichiOnFirstTurn(t *testing.T, g engine.Game, riichiSeat tile.Seat) engine.Game {
	t.Helper()
	for {
		turn, ok := g.Awaiting().(play.AwaitingTurn)
		if ok && turn.Seat == riichiSeat {
			d, _ := g.Decision(turn.Seat)
			drawn := d.Context.(play.TurnAfterDraw).Drawn
			g, _ = act(t, g, turn.Seat, play.RiichiAction(drawn))
			return playDefaultsUntilRoundOver(t, g)
		}
		d, _ := g.Decision(turn.Seat)
		g, _ = act(t, g, turn.Seat, d.Default)
	}
}

func TestReconnectionPayload_WhenTheRoundIsOver_ShouldShowTheEndedRoundAndItsResult(t *testing.T) {
	g, _ := newFixedGame(t, tenpaiSeatOneWall(t))
	fresh := snapshot(t, g, seat(t, 0))

	over := snapshot(t, playDefaultsUntilRoundOver(t, g), seat(t, 0))

	if _, ok := fresh.Get(wire.KeyLatestDiscardSeat); ok {
		t.Error("a snapshot before the first discard names a latest discard")
	}
	for _, c := range []struct {
		key  wire.Key
		want wire.Value
	}{
		{wire.KeyDealer, wire.Int(0)},
		{wire.KeyWind, wire.Int(0)},
		{wire.KeyRoundNumber, wire.Int(0)},
		{wire.KeyRoundInWind, wire.Int(1)},
		{wire.KeyHonba, wire.Int(0)},
		{wire.KeyRiichiSticks, wire.Int(0)},
	} {
		assertMap(t, c.key.String(), wire.Map{{Key: c.key, Value: field(t, over, c.key)}}, wire.Map{{Key: c.key, Value: c.want}})
	}
	result := field(t, over, wire.KeyRoundResult).(wire.Map)
	assertMap(t, "round result head", result[:5], wire.Map{
		{Key: wire.KeyResultType, Value: wire.Int(3)},
		{Key: wire.KeyRiichiSticks, Value: wire.Int(0)},
		{Key: wire.KeyDealer, Value: wire.Int(0)},
		{Key: wire.KeyDoraIndicators, Value: field(t, over, wire.KeyDoraIndicators)},
		{Key: wire.KeyTenpaiSeats, Value: intArray(1)},
	})
	assertMap(t, "scores before payment", wire.Map{{Key: wire.KeyScores, Value: field(t, result, wire.KeyScores)}},
		wire.Map{{Key: wire.KeyScores, Value: scores(250, 250, 250, 250)}})
	if got := seatScores(t, over); !slices.Equal(got, []int{240, 280, 240, 240}) {
		t.Errorf("player scores = %v, want 240, 280, 240, 240", got)
	}
}

func TestReconnectionPayload_WhenARoundEndedBefore_ShouldListItInTheRoundHistory(t *testing.T) {
	g, _ := newFixedGame(t, tenpaiSeatOneWall(t), tenpaiSeatOneWall(t))
	g = riichiOnFirstTurn(t, g, seat(t, 1))
	g, _, refusal := g.DealNextRound()
	if refusal.OK {
		t.Fatalf("DealNextRound refused: %+v", refusal.Value)
	}

	m := snapshot(t, g, seat(t, 0))

	if _, ok := m.Get(wire.KeyRoundResult); ok {
		t.Error("a snapshot of a round in play names a round result")
	}
	assertMap(t, "honba", wire.Map{{Key: wire.KeyHonba, Value: field(t, m, wire.KeyHonba)}}, wire.Map{{Key: wire.KeyHonba, Value: wire.Int(1)}})
	assertMap(t, "history", wire.Map{{Key: wire.KeyRoundHistory, Value: field(t, m, wire.KeyRoundHistory)}}, wire.Map{
		{Key: wire.KeyRoundHistory, Value: wire.Array{wire.Map{
			{Key: wire.KeyWind, Value: wire.Int(0)},
			{Key: wire.KeyDealer, Value: wire.Int(0)},
			{Key: wire.KeyHonba, Value: wire.Int(0)},
			{Key: wire.KeyResultType, Value: wire.Int(3)},
			{Key: wire.KeyRiichiSeats, Value: intArray(1)},
			{Key: wire.KeyWinnerSeat, Value: wire.Array{}},
			{Key: wire.KeyPaoSeat, Value: wire.Array{}},
			{Key: wire.KeyTenpaiSeats, Value: intArray(1)},
			{Key: wire.KeyScoreChanges, Value: scores(-10, 30, -10, -10)},
		}}},
	})
}

func TestReconnectionPayload_ShouldMarkAStandInByItsReasonAndAnAIPlayerFromTheStartAsSuch(t *testing.T) {
	g, _ := newFixedGame(t, tenpaiSeatOneWall(t))
	r := testRoster()
	r.AI[3] = true
	var standIns [tile.SeatCount]play.Option[wire.SeatControlReason]
	standIns[1] = play.Some(wire.SeatControlAbsent)

	m, err := messaging.ReconnectionPayload(g.View(seat(t, 0)).Record, r, standIns)
	if err != nil {
		t.Fatalf("ReconnectionPayload error = %v", err)
	}

	players := field(t, m, wire.KeyPlayers).(wire.Array)
	assertMap(t, "stand-in", players[1].(wire.Map), wire.Map{
		{Key: wire.KeySeat, Value: wire.Int(1)},
		{Key: wire.KeyName, Value: wire.Str("Bob")},
		{Key: wire.KeyAIPlayer, Value: wire.Int(0)},
		{Key: wire.KeyStandInReason, Value: wire.Int(1)},
	})
	assertMap(t, "AI player", players[3].(wire.Map), wire.Map{
		{Key: wire.KeySeat, Value: wire.Int(3)},
		{Key: wire.KeyName, Value: wire.Str("Dave")},
		{Key: wire.KeyAIPlayer, Value: wire.Int(1)},
	})
}
