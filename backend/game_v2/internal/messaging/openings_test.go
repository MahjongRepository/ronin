package messaging_test

import (
	"reflect"
	"slices"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func exportAll() cmp.Option {
	return cmp.Exporter(func(reflect.Type) bool { return true })
}

func held(t *testing.T, a, b int) [2]tile.TileID {
	t.Helper()
	return [2]tile.TileID{id(t, a), id(t, b)}
}

func TestBuildOpening_WhenATurnAfterADrawOffersActions_ShouldListThemInOrderOnTheDraw(t *testing.T) {
	decision := play.Decision{
		Seat:    seat(t, 1),
		Context: play.TurnAfterDraw{Drawn: id(t, 42)},
		Legal: []play.Action{
			play.DiscardAction(id(t, 8)), play.DiscardAction(id(t, 42)), play.RiichiAction(id(t, 8)),
			play.RiichiAction(id(t, 42)), play.TsumoAction(), play.KanAction(play.KanClosed, id(t, 40)),
			play.KanAction(play.KanAdded, id(t, 4)), play.KyuushuAction(),
		},
		Default: play.DiscardAction(id(t, 42)),
	}

	opening := messaging.BuildOpening(decision)

	if opening.Seat != seat(t, 1) || !opening.ReplacesDraw {
		t.Errorf("opening of seat %d replacing the draw %v, want seat 1 replacing it", opening.Seat.Index(), opening.ReplacesDraw)
	}
	assertMap(t, "draw", opening.Payload, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(1)},
		{Key: wire.KeyPackedMove, Value: wire.Int(wire.PackDraw(seat(t, 1), id(t, 42)))},
		{Key: wire.KeyAvailableActions, Value: wire.Array{
			wire.Map{{Key: wire.KeyAction, Value: wire.Int(1)}, {Key: wire.KeyTiles, Value: intArray(8, 42)}},
			wire.Map{{Key: wire.KeyAction, Value: wire.Int(2)}},
			wire.Map{{Key: wire.KeyAction, Value: wire.Int(3)}, {Key: wire.KeyTiles, Value: intArray(10)}},
			wire.Map{{Key: wire.KeyAction, Value: wire.Int(4)}, {Key: wire.KeyTiles, Value: intArray(1)}},
			wire.Map{{Key: wire.KeyAction, Value: wire.Int(5)}},
		}},
	})
}

func TestBuildOpening_WhenATurnAfterADrawOffersOnlyDiscards_ShouldOmitTheOffers(t *testing.T) {
	decision := play.Decision{
		Seat: seat(t, 0), Context: play.TurnAfterDraw{Drawn: id(t, 10)},
		Legal: []play.Action{play.DiscardAction(id(t, 10))}, Default: play.DiscardAction(id(t, 10)),
	}

	assertMap(t, "draw", messaging.BuildOpening(decision).Payload, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(1)},
		{Key: wire.KeyPackedMove, Value: wire.Int(10)},
	})
}

func TestBuildOpening_WhenATurnFollowsTheSeatsOwnCall_ShouldCarryOnlyTheTypeAndTheKuikaeKinds(t *testing.T) {
	decision := play.Decision{
		Seat: seat(t, 0), Context: play.TurnAfterCall{Kuikae: []tile.Kind{4, 7}},
		Legal: []play.Action{play.DiscardAction(id(t, 20))}, Default: play.DiscardAction(id(t, 20)),
	}

	opening := messaging.BuildOpening(decision)

	if opening.ReplacesDraw {
		t.Error("a turn after a call replaces a draw")
	}
	assertMap(t, "turn", opening.Payload, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(12)},
		{Key: wire.KeyKuikaeTiles, Value: intArray(4, 7)},
	})
}

func TestBuildOpening_WhenARonCallerMayAlsoMeld_ShouldSendARonPromptListingItsMelds(t *testing.T) {
	decision := play.Decision{
		Seat:    seat(t, 2),
		Context: play.Call{Tile: id(t, 42), From: seat(t, 1), Source: play.SourceDiscard},
		Legal: []play.Action{
			play.RonAction(), play.KanAction(play.KanOpen, id(t, 42)), play.PonAction(held(t, 41, 43)),
			play.ChiAction(held(t, 36, 40)), play.ChiAction(held(t, 40, 48)), play.PassAction(),
		},
		Default: play.PassAction(),
	}

	assertMap(t, "ron prompt", messaging.BuildOpening(decision).Payload, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(3)},
		{Key: wire.KeyCallType, Value: wire.Int(0)},
		{Key: wire.KeyTileID, Value: wire.Int(42)},
		{Key: wire.KeyFromSeat, Value: wire.Int(1)},
		{Key: wire.KeyCallerSeat, Value: wire.Int(2)},
		{Key: wire.KeyAvailableCalls, Value: wire.Array{
			wire.Map{{Key: wire.KeyCallType, Value: wire.Int(2)}},
			wire.Map{{Key: wire.KeyCallType, Value: wire.Int(0)}, {Key: wire.KeyCallOptions, Value: wire.Array{intArray(41, 43)}}},
			wire.Map{{Key: wire.KeyCallType, Value: wire.Int(1)}, {Key: wire.KeyCallOptions, Value: wire.Array{intArray(36, 40), intArray(40, 48)}}},
		}},
	})
}

func TestBuildOpening_WhenASeatMayOnlyMeld_ShouldSendAMeldPrompt(t *testing.T) {
	decision := play.Decision{
		Seat:    seat(t, 0),
		Context: play.Call{Tile: id(t, 55), From: seat(t, 3), Source: play.SourceDiscard},
		Legal: []play.Action{
			play.PonAction(held(t, 52, 53)), play.PonAction(held(t, 53, 54)), play.ChiAction(held(t, 57, 63)), play.PassAction(),
		},
		Default: play.PassAction(),
	}

	assertMap(t, "meld prompt", messaging.BuildOpening(decision).Payload, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(3)},
		{Key: wire.KeyCallType, Value: wire.Int(1)},
		{Key: wire.KeyTileID, Value: wire.Int(55)},
		{Key: wire.KeyFromSeat, Value: wire.Int(3)},
		{Key: wire.KeyCallerSeat, Value: wire.Int(0)},
		{Key: wire.KeyAvailableCalls, Value: wire.Array{
			wire.Map{{Key: wire.KeyCallType, Value: wire.Int(0)}, {Key: wire.KeyCallOptions, Value: wire.Array{intArray(52, 53), intArray(53, 54)}}},
			wire.Map{{Key: wire.KeyCallType, Value: wire.Int(1)}, {Key: wire.KeyCallOptions, Value: wire.Array{intArray(57, 63)}}},
		}},
	})
}

func TestBuildOpening_WhenAKanCanBeRobbed_ShouldSendAChankanPromptNamingTheKan(t *testing.T) {
	for _, c := range []struct {
		source play.CallSource
		kan    string
	}{{play.SourceClosedKan, "closed"}, {play.SourceAddedKan, "added"}} {
		decision := play.Decision{
			Seat: seat(t, 1), Context: play.Call{Tile: id(t, 8), From: seat(t, 0), Source: c.source},
			Legal: []play.Action{play.RonAction(), play.PassAction()}, Default: play.PassAction(),
		}

		assertMap(t, c.kan+" chankan prompt", messaging.BuildOpening(decision).Payload, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(3)},
			{Key: wire.KeyCallType, Value: wire.Int(2)},
			{Key: wire.KeyTileID, Value: wire.Int(8)},
			{Key: wire.KeyFromSeat, Value: wire.Int(0)},
			{Key: wire.KeyKanType, Value: wire.Str(c.kan)},
			{Key: wire.KeyCallerSeat, Value: wire.Int(1)},
		})
	}
}

func TestPlaceOpenings_ShouldReplaceTheOpenedDrawAndPutEveryOtherOpeningAheadOfTheFuritenChanges(t *testing.T) {
	discard := play.Emitted{To: play.ToAll(), Event: play.Discarded{Seat: seat(t, 0), Tile: id(t, 1)}}
	drawToTwo := play.Emitted{To: play.ToSeat(seat(t, 2)), Event: play.Drew{Seat: seat(t, 2), Tile: id(t, 2)}}
	drawToOne := play.Emitted{To: play.ToSeat(seat(t, 1)), Event: play.Drew{Seat: seat(t, 1), Tile: id(t, 3)}}
	furiten := play.Emitted{To: play.ToSeat(seat(t, 3)), Event: play.FuritenChanged{Seat: seat(t, 3), Furiten: true}}
	turn := messaging.Opening{Seat: seat(t, 1), Payload: wire.Map{{Key: wire.KeyEventType, Value: wire.Int(1)}}, ReplacesDraw: true}
	prompt := messaging.Opening{Seat: seat(t, 3), Payload: wire.Map{{Key: wire.KeyEventType, Value: wire.Int(3)}}}

	placed := slices.Collect(messaging.PlaceOpenings([]play.Emitted{discard, drawToTwo, drawToOne, furiten}, []messaging.Opening{turn, prompt}))
	unfuriten := slices.Collect(messaging.PlaceOpenings([]play.Emitted{discard}, []messaging.Opening{prompt}))

	want := []messaging.Placed{
		{Event: discard},
		{Event: drawToTwo},
		{Opening: play.Some(turn)},
		{Opening: play.Some(prompt)},
		{Event: furiten},
	}
	if diff := cmp.Diff(want, placed, exportAll()); diff != "" {
		t.Errorf("placed (-want +got):\n%s", diff)
	}
	if diff := cmp.Diff([]messaging.Placed{{Event: discard}, {Opening: play.Some(prompt)}}, unfuriten,
		exportAll()); diff != "" {
		t.Errorf("placed without furiten (-want +got):\n%s", diff)
	}
}
