package messaging_test

import (
	"encoding/hex"
	"errors"
	"reflect"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func payload(t *testing.T, e play.Event, record play.SeatRecord) wire.Map {
	t.Helper()
	m, err := messaging.EventPayload(e, func() messaging.Table { return messaging.Table{Roster: testRoster(), Record: record} })
	if err != nil {
		t.Fatalf("EventPayload(%T) error = %v", e, err)
	}

	return m
}

func notenStart(t *testing.T) (play.GameStarted, []play.RoundStarted, play.Drew) {
	t.Helper()
	wall := fixedWall(t, [tile.SeatCount][]tile.TileID{junk(t, 0), junk(t, 1), junk(t, 2), junk(t, 3)}, ids(t, 135))
	_, events := newFixedGame(t, wall)

	var started play.GameStarted
	var dealt []play.RoundStarted
	var drew play.Drew
	for _, e := range events {
		switch event := e.Event.(type) {
		case play.GameStarted:
			started = event
		case play.RoundStarted:
			dealt = append(dealt, event)
		case play.Drew:
			drew = event
		case play.DrewNotice, play.Discarded, play.RiichiDeposited, play.FuritenChanged, play.Called,
			play.PaoAssigned, play.DoraRevealed, play.RoundEnded, play.GameEnded:
		}
	}

	return started, dealt, drew
}

func TestEventPayload_WhenAGameStarts_ShouldShapeTheStartTheDealsAndTheDealersDraw(t *testing.T) {
	started, dealt, drew := notenStart(t)

	assertMap(t, "game started", payload(t, started, play.SeatRecord{}), wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(8)},
		{Key: wire.KeyGameID, Value: wire.Str("game1")},
		{Key: wire.KeyGameType, Value: wire.Int(0)},
		{Key: wire.KeyPlayers, Value: wire.Array{
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(0)}, {Key: wire.KeyName, Value: wire.Str("Alice")}, {Key: wire.KeyAIPlayer, Value: wire.Int(0)}},
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(1)}, {Key: wire.KeyName, Value: wire.Str("Bob")}, {Key: wire.KeyAIPlayer, Value: wire.Int(0)}},
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(2)}, {Key: wire.KeyName, Value: wire.Str("Charlie")}, {Key: wire.KeyAIPlayer, Value: wire.Int(0)}},
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(3)}, {Key: wire.KeyName, Value: wire.Str("Dave")}, {Key: wire.KeyAIPlayer, Value: wire.Int(0)}},
		}},
		{Key: wire.KeyDealer, Value: wire.Int(0)},
		{Key: wire.KeyDealerDice, Value: wire.Array{intArray(1, 1), intArray(1, 1)}},
		{Key: wire.KeyRiichiStickValue, Value: wire.Int(10)},
	})
	dora := field(t, payload(t, dealt[1], play.SeatRecord{}), wire.KeyDoraIndicators)
	assertMap(t, "seat 1's deal", payload(t, dealt[1], play.SeatRecord{}), wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(9)},
		{Key: wire.KeySeat, Value: wire.Int(1)},
		{Key: wire.KeyWind, Value: wire.Int(0)},
		{Key: wire.KeyRoundNumber, Value: wire.Int(0)},
		{Key: wire.KeyRoundInWind, Value: wire.Int(1)},
		{Key: wire.KeyDealer, Value: wire.Int(0)},
		{Key: wire.KeyCurrentPlayer, Value: wire.Int(0)},
		{Key: wire.KeyDoraIndicators, Value: dora},
		{Key: wire.KeyHonba, Value: wire.Int(0)},
		{Key: wire.KeyRiichiSticks, Value: wire.Int(0)},
		{Key: wire.KeyMyTiles, Value: intArray(1, 9, 17, 25, 41, 49, 57, 65, 73, 81, 89, 97, 105)},
		{Key: wire.KeyPlayers, Value: wire.Array{
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(0)}, {Key: wire.KeyScore, Value: wire.Int(250)}},
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(1)}, {Key: wire.KeyScore, Value: wire.Int(250)}},
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(2)}, {Key: wire.KeyScore, Value: wire.Int(250)}},
			wire.Map{{Key: wire.KeySeat, Value: wire.Int(3)}, {Key: wire.KeyScore, Value: wire.Int(250)}},
		}},
		{Key: wire.KeyDice, Value: intArray(1, 1)},
		{Key: wire.KeyTilesRemaining, Value: wire.Int(70)},
	})
	assertMap(t, "dealer's draw", payload(t, drew, play.SeatRecord{}), wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(1)},
		{Key: wire.KeyPackedMove, Value: wire.Int(135)},
	})
	assertMap(t, "dealer's replayed draw", messaging.ReplayDrawPayload(drew, 69), wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(1)},
		{Key: wire.KeyPackedMove, Value: wire.Int(135)},
		{Key: wire.KeyTilesRemaining, Value: wire.Int(69)},
	})
}

func TestReplayRoundStartedPayload_ShouldMergeTheDealsIntoOneRecordOfEveryHand(t *testing.T) {
	_, dealt, _ := notenStart(t)

	merged := messaging.ReplayRoundStartedPayload(dealt)

	wantKeys := []wire.Key{
		wire.KeyEventType, wire.KeyWind, wire.KeyRoundNumber, wire.KeyRoundInWind, wire.KeyDealer, wire.KeyCurrentPlayer,
		wire.KeyDoraIndicators, wire.KeyHonba, wire.KeyRiichiSticks, wire.KeyPlayers, wire.KeyDice, wire.KeyTilesRemaining,
	}
	if got := keys(merged); !slices.Equal(got, wantKeys) {
		t.Errorf("merged keys = %v, want %v", got, wantKeys)
	}

	players := field(t, merged, wire.KeyPlayers).(wire.Array)
	assertMap(t, "seat 3 in the merged deal", players[3].(wire.Map), wire.Map{
		{Key: wire.KeySeat, Value: wire.Int(3)},
		{Key: wire.KeyScore, Value: wire.Int(250)},
		{Key: wire.KeyTiles, Value: intArray(3, 11, 19, 27, 43, 51, 59, 67, 75, 83, 91, 99, 107)},
	})
}

func TestEventPayload_WhenAMoveHasTheShapeOfPython_ShouldEncodeToItsGoldenBytes(t *testing.T) {
	for _, c := range []struct {
		name  string
		event play.Event
		hex   string
	}{
		{"discard", play.Discarded{Seat: seat(t, 0), Tile: id(t, 37)}, "8201020625"},
		{"pao_assigned", play.PaoAssigned{Seat: seat(t, 2), Liable: seat(t, 0)}, "83010e32022400"},
	} {
		t.Run(c.name, func(t *testing.T) {
			m, err := messaging.EventPayload(c.event, func() messaging.Table {
				t.Errorf("%s: EventPayload asked for the table", c.name)
				return messaging.Table{}
			})
			if err != nil {
				t.Fatalf("%s: EventPayload error = %v", c.name, err)
			}

			got, err := wire.Encode(m)
			if err != nil || hex.EncodeToString(got) != c.hex {
				t.Errorf("%s: Encode = %x, %v; want %s", c.name, got, err, c.hex)
			}
		})
	}
}

func TestEventPayload_WhenAnEventIsATableSignal_ShouldNameOnlyItsFacts(t *testing.T) {
	for _, c := range []struct {
		name  string
		event play.Event
		want  wire.Map
	}{
		{"draw notice", play.DrewNotice{Seat: seat(t, 2), Rinshan: true}, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(13)}, {Key: wire.KeySeat, Value: wire.Int(2)},
		}},
		{"riichi deposit", play.RiichiDeposited{Seat: seat(t, 1), Score: 24000, RiichiSticks: 2}, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(5)},
			{Key: wire.KeySeat, Value: wire.Int(1)},
			{Key: wire.KeyScore, Value: wire.Int(240)},
			{Key: wire.KeyRiichiSticks, Value: wire.Int(2)},
		}},
		{"furiten", play.FuritenChanged{Seat: seat(t, 3), Furiten: true}, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(11)}, {Key: wire.KeyFuriten, Value: wire.Bool(true)},
		}},
		{"dora", play.DoraRevealed{Indicator: id(t, 77)}, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(6)}, {Key: wire.KeyTileID, Value: wire.Int(77)},
		}},
	} {
		t.Run(c.name, func(t *testing.T) {
			assertMap(t, c.name, payload(t, c.event, play.SeatRecord{}), c.want)
		})
	}
}

func TestEventPayload_WhenAnAddedKanIsCalled_ShouldPackTheCopyItAdded(t *testing.T) {
	kan := play.Called{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldAddedKan, Tiles: ids(t, 4, 5, 6, 7), Called: play.Some(id(t, 5)), From: play.Some(seat(t, 2)),
		Added: play.Some(id(t, 6)),
	}}

	m := payload(t, kan, play.SeatRecord{})

	if got := keys(m); !slices.Equal(got, []wire.Key{wire.KeyEventType, wire.KeyPackedMeld}) {
		t.Fatalf("meld keys = %v", got)
	}

	meld, err := wire.UnpackMeld(int(field(t, m, wire.KeyPackedMeld).(wire.Int)))
	want := wire.Meld{
		Caller: seat(t, 0), Kind: play.MeldAddedKan, Tiles: ids(t, 4, 5, 6, 7), Called: play.Some(id(t, 5)),
		From: play.Some(seat(t, 2)), Added: play.Some(id(t, 6)),
	}
	if err != nil || !reflect.DeepEqual(meld, want) {
		t.Errorf("UnpackMeld = %+v, %v; want %+v", meld, err, want)
	}
}

func TestEventPayload_WhenAMeldIsNoMeldOfItsKind_ShouldReportIt(t *testing.T) {
	chi := play.Called{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldChi, Tiles: ids(t, 0, 4, 8), Called: play.Some(id(t, 0)), From: play.Some(seat(t, 2)),
	}}

	_, err := messaging.EventPayload(chi, func() messaging.Table { return messaging.Table{} })

	if _, isType := errors.AsType[wire.InvalidMeldError](err); !isType {
		t.Errorf("EventPayload error = %v, want an InvalidMeldError", err)
	}
}

func TestEventPayload_WhenTheGameEndsWithSticksUnawarded_ShouldNameTheirCountBonusRoundsAndCause(t *testing.T) {
	ended := play.GameEnded{Standings: play.Standings{
		Cause:      play.EndExtensionLimit,
		Scores:     [tile.SeatCount]int{23000, 31000, 24000, 22000},
		Placements: [tile.SeatCount]int{3, 1, 2, 4},
		Points:     [tile.SeatCount]int{-170, 510, 40, -380},
	}}
	record := play.SeatRecord{
		Header:           play.RoundHeader{RoundNumber: 7},
		RiichiStickValue: 1000,
		History: []play.FinishedRound{{
			Header:      play.RoundHeader{RoundNumber: 7, RiichiSticks: 1},
			Result:      play.ExhaustiveDraw{},
			RiichiSeats: []tile.Seat{seat(t, 1)},
		}},
	}

	m := payload(t, ended, record)

	standing := func(s, place, score, final int) wire.Map {
		return wire.Map{
			{Key: wire.KeySeat, Value: wire.Int(s)},
			{Key: wire.KeyPlace, Value: wire.Int(place)},
			{Key: wire.KeyScore, Value: wire.Int(score)},
			{Key: wire.KeyFinalScore, Value: wire.Int(final)},
		}
	}

	assertMap(t, "game end", m, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(10)},
		{Key: wire.KeyWinnerSeat, Value: wire.Int(1)},
		{Key: wire.KeyStandings, Value: wire.Array{
			standing(1, 1, 310, 510), standing(2, 2, 240, 40), standing(0, 3, 230, -170), standing(3, 4, 220, -380),
		}},
		{Key: wire.KeyLeftoverBonus, Value: wire.Int(20)},
		{Key: wire.KeyLeftoverRiichi, Value: wire.Int(2)},
		{Key: wire.KeyRoundCount, Value: wire.Int(8)},
		{Key: wire.KeyEndCause, Value: wire.Str("extension_limit")},
	})
}

func TestEventPayload_WhenTwoSeatsShareFirstPlace_ShouldListBothFromTheFirstDealerOnWithTheSharedPlace(t *testing.T) {
	ended := play.GameEnded{Standings: play.Standings{
		Cause:      play.EndLength,
		Scores:     [tile.SeatCount]int{35500, 25000, 35500, 24000},
		Placements: [tile.SeatCount]int{1, 3, 1, 4},
		Points:     [tile.SeatCount]int{255, -150, 255, -360},
	}}
	record := play.SeatRecord{FirstDealer: seat(t, 2), RiichiStickValue: 1000}

	m := payload(t, ended, record)

	winner, _ := m.Get(wire.KeyWinnerSeat)
	standings, _ := m.Get(wire.KeyStandings)
	var seats, places []wire.Value
	for _, standing := range standings.(wire.Array) {
		s, _ := standing.(wire.Map).Get(wire.KeySeat)
		place, _ := standing.(wire.Map).Get(wire.KeyPlace)
		seats, places = append(seats, s), append(places, place)
	}
	if winner != wire.Int(2) || !slices.Equal(seats, []wire.Value{wire.Int(2), wire.Int(0), wire.Int(1), wire.Int(3)}) {
		t.Errorf("winner = %v, standings seats = %v, want 2 and [2 0 1 3]", winner, seats)
	}
	if !slices.Equal(places, []wire.Value{wire.Int(1), wire.Int(1), wire.Int(3), wire.Int(4)}) {
		t.Errorf("standings places = %v, want [1 1 3 4]", places)
	}
}

func TestReplaySeatControlPayload_WhenASeatChangesHands_ShouldWriteARecordTheReplayAccepts(t *testing.T) {
	left := messaging.ReplaySeatControlPayload(seat(t, 2), play.Some(wire.SeatControlLeft))
	back := messaging.ReplaySeatControlPayload(seat(t, 2), play.Option[wire.SeatControlReason]{})

	assertMap(t, "AI replacement", left, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventSeatControl)},
		{Key: wire.KeySeat, Value: wire.Int(2)},
		{Key: wire.KeyAIPlayer, Value: wire.Int(1)},
		{Key: wire.KeySeatControlReason, Value: wire.Int(wire.SeatControlLeft)},
	})
	assertMap(t, "human return", back, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventSeatControl)},
		{Key: wire.KeySeat, Value: wire.Int(2)},
		{Key: wire.KeyAIPlayer, Value: wire.Int(0)},
	})
	_, err := messaging.EncodeReplayRecords([]wire.Map{left, back})
	if err != nil {
		t.Errorf("EncodeReplayRecords error = %v", err)
	}
}
