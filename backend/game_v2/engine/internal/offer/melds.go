package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// OpenKanHandTiles is how many held copies of the discard's kind an open kan takes.
const OpenKanHandTiles = 3

const (
	ponHandTiles    = 2
	lastSuitValue   = 8
	maxChiShapes    = 3
	maxLooksPerKind = 2
	maxChiOptions   = maxChiShapes * maxLooksPerKind * maxLooksPerKind
	maxKuikaeKinds  = 2
)

// CheckedMeldOffers returns MeldOffers for a hand given from outside the engine; a
// meld.DuplicateTileError for the first tile id held twice in hand.
func CheckedMeldOffers(
	hand []tile.TileID, inRiichi bool, seat, from tile.Seat, discard tile.TileID,
	kans [tile.SeatCount]int, liveTiles int,
) ([]play.Action, error) {
	if err := meld.CheckHandInput(hand, nil); err != nil {
		return nil, err
	}
	return MeldOffers(hand, inRiichi, seat, from, discard, kans, liveTiles), nil
}

// MeldOffers returns the meld calls seat is offered on from's discard, beside the kans of each
// seat, 0 or more: an open kan, each pon of PonOptions, then each chi of ChiOptions; none to the
// discarder, from an empty live wall or once four kans by more than one seat abort the round.
func MeldOffers(
	hand []tile.TileID, inRiichi bool, seat, from tile.Seat, discard tile.TileID,
	kans [tile.SeatCount]int, liveTiles int,
) []play.Action {
	if seat == from || liveTiles == 0 || IsFourKans(kans) {
		return nil
	}

	openKan := holdsOpenKan(hand, inRiichi, discard) && MayAddKan(kans, liveTiles)
	pons := PonOptions(hand, inRiichi, discard)
	var chiOptions [maxChiOptions][2]tile.TileID
	chis := chiOptions[:0]
	if seat.Kamicha() == from {
		chis = appendChiOptions(chis, hand, inRiichi, discard)
	}
	count := len(pons) + len(chis)
	if openKan {
		count++
	}
	if count == 0 {
		return nil
	}

	offers := make([]play.Action, 0, count)
	if openKan {
		offers = append(offers, play.KanAction(play.KanOpen, discard))
	}
	for _, pair := range pons {
		offers = append(offers, play.PonAction(pair))
	}
	for _, pair := range chis {
		offers = append(offers, play.ChiAction(pair))
	}
	return offers
}

// PonOptions returns the hand tiles of each pon of the discard's kind, one pair per look, in hand
// order: a held red five with a plain copy, then two plain copies; none in riichi. A pon of the
// red five itself takes plain copies only, so it is offered once.
func PonOptions(hand []tile.TileID, inRiichi bool, discard tile.TileID) [][2]tile.TileID {
	if inRiichi {
		return nil
	}

	var red, plain []tile.TileID
	for held := range tile.HeldCopies(hand, discard.Kind()) {
		if isRed(held) {
			red = append(red, held)
		} else {
			plain = append(plain, held)
		}
	}

	var options [][2]tile.TileID
	if len(red) > 0 && len(plain) > 0 {
		options = append(options, [2]tile.TileID{red[0], plain[0]})
	}
	if len(plain) >= ponHandTiles {
		options = append(options, [2]tile.TileID{plain[0], plain[1]})
	}
	return options
}

func holdsOpenKan(hand []tile.TileID, inRiichi bool, discard tile.TileID) bool {
	return !inRiichi && heldCount(hand, discard.Kind()) >= OpenKanHandTiles
}

func heldCount(hand []tile.TileID, kind tile.Kind) int {
	count := 0
	for range tile.HeldCopies(hand, kind) {
		count++
	}
	return count
}

// ChiOptions returns the hand tiles of each chi the kamicha's discard offers, one pair per shape,
// a red five making its own: the discard as the lowest, the middle, then the highest tile, each
// low look in hand order before each high one. None in riichi, on an honor, or for a pair that
// leaves no discard kuikae allows.
func ChiOptions(hand []tile.TileID, inRiichi bool, discard tile.TileID) [][2]tile.TileID {
	return appendChiOptions(nil, hand, inRiichi, discard)
}

func appendChiOptions(
	options [][2]tile.TileID, hand []tile.TileID, inRiichi bool, discard tile.TileID,
) [][2]tile.TileID {
	kind := discard.Kind()
	if inRiichi || kind.IsHonor() {
		return options
	}

	value := kind.Simplify()
	var shapeKinds [maxChiShapes][2]tile.Kind
	shapes := shapeKinds[:0]
	if value+2 <= lastSuitValue {
		shapes = append(shapes, [2]tile.Kind{kind + 1, kind + 2})
	}
	if value >= 1 && value < lastSuitValue {
		shapes = append(shapes, [2]tile.Kind{kind - 1, kind + 1})
	}
	if value >= 2 {
		shapes = append(shapes, [2]tile.Kind{kind - 2, kind - 1})
	}

	for _, shape := range shapes {
		var lowLooks, highLooks [maxLooksPerKind]tile.TileID
		highs := appendLooks(highLooks[:0], hand, shape[1])
		for _, low := range appendLooks(lowLooks[:0], hand, shape[0]) {
			for _, high := range highs {
				pair := [2]tile.TileID{low, high}
				if leavesLegalDiscard(hand, discard, pair) {
					options = append(options, pair)
				}
			}
		}
	}
	return options
}

func appendLooks(found, hand []tile.TileID, kind tile.Kind) []tile.TileID {
	for held := range tile.HeldCopies(hand, kind) {
		seen := slices.ContainsFunc(found, func(look tile.TileID) bool { return isRed(look) == isRed(held) })
		if !seen {
			found = append(found, held)
		}
	}
	return found
}

func leavesLegalDiscard(hand []tile.TileID, discard tile.TileID, pair [2]tile.TileID) bool {
	var kinds [maxKuikaeKinds]tile.Kind
	kuikae := appendChiKuikaeKinds(kinds[:0], discard.Kind(), pair)
	for _, held := range hand {
		if !slices.Contains(pair[:], held) && !slices.Contains(kuikae, held.Kind()) {
			return true
		}
	}
	return false
}

// KuikaeKinds returns the kinds kuikae forbids right after calling discard: its kind, after a chi
// on an end also the kind past the other end; none after an open kan.
func KuikaeKinds(discard tile.TileID, call play.MeldCall) []tile.Kind {
	called := discard.Kind()
	var pair [2]tile.TileID
	switch c := call.(type) {
	case play.OpenKanCall:
		return nil
	case play.PonCall:
		return []tile.Kind{called}
	case play.ChiCall:
		pair = c.Held
	}
	return appendChiKuikaeKinds(nil, called, pair)
}

func appendChiKuikaeKinds(kinds []tile.Kind, called tile.Kind, pair [2]tile.TileID) []tile.Kind {
	kinds = append(kinds, called)
	low, high := pair[0].Kind(), pair[1].Kind()
	lowest, highest := min(low, high, called), max(low, high, called)
	switch {
	case called == lowest && highest.Simplify() < lastSuitValue:
		kinds = append(kinds, highest+1)
	case called == highest && lowest.Simplify() > 0:
		kinds = append(kinds, lowest-1)
	}
	return kinds
}

func paoSeat(melds []play.MeldView, calledKind tile.Kind, discarder tile.Seat) play.Option[tile.Seat] {
	dragons, winds := tile.DragonKinds(), tile.WindKinds()
	var set []tile.Kind
	switch {
	case slices.Contains(dragons[:], calledKind):
		set = dragons[:]
	case slices.Contains(winds[:], calledKind):
		set = winds[:]
	default:
		return play.Option[tile.Seat]{}
	}

	heldSets := 0
	for _, view := range melds {
		if len(view.Tiles) > 0 && slices.Contains(set, view.Tiles[0].Kind()) {
			heldSets++
		}
	}
	if heldSets != len(set)-1 {
		return play.Option[tile.Seat]{}
	}
	return play.Some(discarder)
}

// PaoOfMeld returns the seat a meld view made liable, after the earlier melds of its seat: the
// discarder of a pon or open kan that completes the caller's third dragon set or fourth wind set.
// An added kan, a chi, a closed kan and a meld with no tiles make nobody liable.
func PaoOfMeld(earlier []play.MeldView, view play.MeldView) play.Option[tile.Seat] {
	isPonOrOpenKan := view.Kind == play.MeldPon || view.Kind == play.MeldOpenKan
	if !view.From.OK || !isPonOrOpenKan || len(view.Tiles) == 0 {
		return play.Option[tile.Seat]{}
	}
	return paoSeat(earlier, view.Tiles[0].Kind(), view.From.Value)
}

// NewMeldView returns the meld a call makes from the called tile and the hand tiles it takes,
// its tiles sorted by id.
func NewMeldView(kind play.MeldKind, called tile.TileID, taken []tile.TileID, from tile.Seat) play.MeldView {
	tiles := append(slices.Clone(taken), called)
	slices.SortFunc(tiles, tile.TileID.Compare)
	return play.MeldView{Kind: kind, Tiles: tiles, Called: play.Some(called), From: play.Some(from)}
}
