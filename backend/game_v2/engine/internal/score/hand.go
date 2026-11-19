package score

import (
	"cmp"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	sextupleYakumanHan = 78
	meldTiles          = 3
	winningHandTiles   = 14
)

// Hand is the tiles of a winning hand: Concealed are the tiles outside the declared melds, the
// winning tile not among them, 13 less 3 for each meld.
type Hand struct {
	Concealed []tile.Tile
	WinTile   tile.Tile
	Melds     []meld.Meld
}

// Dora is the dora indicators; the ura indicators count only for a riichi.
type Dora struct {
	Indicators    []tile.Tile
	UraIndicators []tile.Tile
}

// HandValue is the value of a winning hand's most expensive reading. Value counts the dora; Limit
// is absent below mangan; Payment holds the honba; Total is what the winner gains, the payment
// plus 1000 per riichi stick. Yaku is sorted by yaku id, the dora counted in Dora instead, which is
// all 0 for a yakuman. FuDetails are unrounded, sorted by fu from most to least, and empty for
// kokushi musou.
type HandValue struct {
	Value     play.Value
	Limit     play.Option[play.Limit]
	Payment   play.Payment
	Total     int
	Yaku      []Yaku
	Dora      play.DoraCount
	FuDetails []FuDetail
}

// EstimateHandValue values a winning hand. The hand is split into every reading of its concealed
// tiles plus the winning tile, each scored once per block the winning tile can complete, and the
// most expensive is returned: the highest total, then a real yakuman over a counted one, then
// more double-yakuman forms, then the given winning tile, then more han, then more fu, then more
// unrounded fu, and on a full tie the first reading. Dora count from the indicators, red fives
// from the tiles, and ura dora only with a riichi.
//
// A tenhou hand has no winning tile, so every kind in it is tried as the winning tile: another
// kind replaces h.WinTile only when it pays more or names a double-yakuman form, so the payment
// never depends on h.WinTile.
//
// The checks run in order and the first failure is returned: a WrongTileCountError, a
// tile.TooManyCopiesError over the concealed tiles, the winning tile and the melds, then the
// situation's OpenHandRiichiError, RinshanWithoutKanError, IppatsuWithRinshanError,
// FirstTurnWithMeldError, FirstTurnSpecialWinError, FirstTurnWithRiichiError and
// FirstTurnDealerRonError; then a NotWinningError when no reading wins, and a NoYakuError when
// the most expensive reading has no yaku.
func EstimateHandValue(h Hand, situation Situation, dora Dora, rules Rules) (HandValue, error) {
	counts, err := countHand(h)
	if err != nil {
		return HandValue{}, err
	}
	err = validateSituation(situation, h.Melds)
	if err != nil {
		return HandValue{}, err
	}

	doraCount := play.DoraCount{
		Dora:    countDoraForHand(counts.tiles, dora.Indicators),
		AkaDora: counts.akaDora,
	}
	if situation.Riichi.OK {
		doraCount.UraDora = countDoraForHand(counts.tiles, dora.UraIndicators)
	}
	open := slices.ContainsFunc(h.Melds, meld.Meld.IsOpen)
	winning := func(win tile.Kind) winningHand {
		return winningHand{
			input: yakuInput{
				counts:    counts.tiles,
				kinds:     counts.kinds,
				win:       win,
				hasMelds:  len(h.Melds) > 0,
				open:      open,
				situation: situation,
				rules:     rules,
			},
			isGivenWinTile: win == h.WinTile.Kind(),
			dora:           doraCount,
		}
	}

	winKinds := tile.KindsFromBits(uint64(1) << h.WinTile.Kind())
	if isTenhou(situation) {
		winKinds = tile.KindsFromBits(counts.kinds)
	}
	melds := hand.MeldSetsOf(h.Melds)
	isKokushi := counts.readings.Len() == 0 && len(h.Melds) == 0 && isKokushiMusou(counts.tiles)
	var best bestHand
	for win := range winKinds.All() {
		scoring := winning(win)
		for decomposition := range counts.readings.All() {
			reading := decomposition.Reading(melds)
			for block := range decomposition.WinBlocks(win) {
				best.offer(scoring.score(reading, block))
			}
		}
		if isKokushi {
			best.offer(scoring.scoreKokushi())
		}
	}
	return best.value()
}

func isTenhou(situation Situation) bool {
	return situation.FirstTurn && situation.IsDealer() && situation.Win == WinTsumo
}

type handCounts struct {
	tiles    [tile.KindCount]uint8
	kinds    uint64
	akaDora  int
	readings hand.Decompositions
}

func countHand(h Hand) (handCounts, error) {
	if len(h.Concealed)+1+len(h.Melds)*meldTiles != winningHandTiles {
		return handCounts{}, WrongTileCountError{Concealed: len(h.Concealed), Melds: len(h.Melds)}
	}

	var counts handCounts
	var concealed [tile.KindCount]uint8
	add := func(t tile.Tile) {
		counts.tiles[t.Kind()]++
		counts.kinds |= uint64(1) << t.Kind()
		if t.IsRed() {
			counts.akaDora++
		}
	}
	for _, t := range h.Concealed {
		add(t)
		concealed[t.Kind()]++
	}
	add(h.WinTile)
	concealed[h.WinTile.Kind()]++
	for _, m := range h.Melds {
		for _, t := range m.Tiles() {
			add(t)
		}
	}

	_, err := tile.CountsFromArray(counts.tiles)
	if err != nil {
		return handCounts{}, err
	}
	concealedCounts, concealedErr := tile.CountsFromArray(concealed)
	readings, divideErr := hand.Divide(concealedCounts)
	counts.readings = readings
	return counts, cmp.Or(concealedErr, divideErr)
}

func validateSituation(situation Situation, melds []meld.Meld) error {
	riichi := situation.Riichi
	firstTurn := situation.FirstTurn
	switch {
	case riichi.OK && slices.ContainsFunc(melds, meld.Meld.IsOpen):
		return OpenHandRiichiError{}
	case situation.Win == WinRinshan && !slices.ContainsFunc(melds, meld.Meld.IsKan):
		return RinshanWithoutKanError{}
	case situation.Win == WinRinshan && riichi.OK && riichi.Value.Ippatsu:
		return IppatsuWithRinshanError{}
	case firstTurn && len(melds) > 0:
		return FirstTurnWithMeldError{}
	case firstTurn && situation.Win != WinRon && situation.Win != WinTsumo:
		return FirstTurnSpecialWinError{}
	case firstTurn && riichi.OK:
		return FirstTurnWithRiichiError{}
	case firstTurn && situation.IsDealer() && !situation.Win.IsTsumo():
		return FirstTurnDealerRonError{}
	default:
		return nil
	}
}

type winningHand struct {
	input          yakuInput
	isGivenWinTile bool
	dora           play.DoraCount
}

type scored struct {
	value   play.Value
	limit   play.Option[play.Limit]
	payment play.Payment
	total   int
	dora    play.DoraCount
}

type calculatedHand struct {
	scored         scored
	hasYaku        bool
	isGivenWinTile bool
	yaku           yakuList
	han            int
	fu             int
	fuDetails      fuDetails
}

func (w winningHand) scoreValue(value play.Value, dora play.DoraCount) scored {
	situation := w.input.situation
	limit, payment := paymentOf(value, situation.Win, situation.SeatWind, situation.Honba, w.input.rules)
	return scored{
		value:   value,
		limit:   limit,
		payment: payment,
		total:   payment.Sum() + RiichiSticksBonus(situation.RiichiSticks),
		dora:    dora,
	}
}

func (w winningHand) score(reading hand.Reading, winBlock hand.WinBlock) calculatedHand {
	in := w.input
	details, fu := calculateFu(fuInput{
		reading:  reading,
		winBlock: winBlock,
		win:      in.win,
		tsumo:    in.situation.Win.IsTsumo(),
		rules:    in.rules,
		valued:   in.valuedKinds(),
		open:     in.open,
	})

	yaku := in.evaluate(reading, winBlock)
	hasYakuman := slices.ContainsFunc(yaku, Yaku.isYakuman)
	if hasYakuman {
		yaku = slices.DeleteFunc(yaku, Yaku.isNotYakuman)
	}
	han := sumHan(yaku)
	hasYaku := han > 0

	var dora play.DoraCount
	if hasYaku && !hasYakuman {
		dora = w.dora
	}
	han = min(han+dora.Dora+dora.AkaDora+dora.UraDora, sextupleYakumanHan)

	calculated := calculatedHand{
		hasYaku:        hasYaku,
		isGivenWinTile: w.isGivenWinTile,
		yaku:           yaku,
		han:            han,
		fu:             fu,
		fuDetails:      details,
	}
	switch {
	case hasYakuman:
		calculated.scored = w.scoreValue(play.Yakuman{Count: han / singleYakumanHan, Fu: play.Some(fu)}, dora)
	case hasYaku:
		calculated.scored = w.scoreValue(play.Han{Han: han, Fu: fu}, dora)
	}
	return calculated
}

func (w winningHand) scoreKokushi() calculatedHand {
	yaku := w.input.evaluateKokushi()
	han := sumHan(yaku)
	return calculatedHand{
		scored:         w.scoreValue(play.Yakuman{Count: han / singleYakumanHan}, play.DoraCount{}),
		hasYaku:        true,
		isGivenWinTile: w.isGivenWinTile,
		yaku:           yaku,
		han:            han,
	}
}

func (y Yaku) isYakuman() bool {
	return y.ID.IsYakuman()
}

func (y Yaku) isNotYakuman() bool {
	return !y.ID.IsYakuman()
}

func sumHan(yaku yakuList) int {
	han := 0
	for _, y := range yaku {
		han += y.Han
	}
	return han
}

type handRank struct {
	total          int
	hasYakuman     bool
	doubleForms    int
	isGivenWinTile bool
	han            int
	fu             int
	unroundedFu    int
}

func (c calculatedHand) rank() handRank {
	total := -1
	if c.hasYaku {
		total = c.scored.total
	}
	doubleForms := 0
	for _, y := range c.yaku {
		if y.ID.IsDoubleYakuman() {
			doubleForms++
		}
	}
	return handRank{
		total:          total,
		hasYakuman:     slices.ContainsFunc(c.yaku, Yaku.isYakuman),
		doubleForms:    doubleForms,
		isGivenWinTile: c.isGivenWinTile,
		han:            c.han,
		fu:             c.fu,
		unroundedFu:    c.fuDetails.total(),
	}
}

func compareRanks(a, b handRank) int {
	return cmp.Or(
		cmp.Compare(a.total, b.total),
		compareBools(a.hasYakuman, b.hasYakuman),
		cmp.Compare(a.doubleForms, b.doubleForms),
		compareBools(a.isGivenWinTile, b.isGivenWinTile),
		cmp.Compare(a.han, b.han),
		cmp.Compare(a.fu, b.fu),
		cmp.Compare(a.unroundedFu, b.unroundedFu),
	)
}

func compareBools(a, b bool) int {
	switch {
	case a == b:
		return 0
	case a:
		return 1
	default:
		return -1
	}
}

type bestHand struct {
	rank    handRank
	hand    calculatedHand
	offered bool
}

func (b *bestHand) offer(c calculatedHand) {
	rank := c.rank()
	if !b.offered || compareRanks(rank, b.rank) > 0 {
		*b = bestHand{rank: rank, hand: c, offered: true}
	}
}

func (b bestHand) value() (HandValue, error) {
	switch {
	case !b.offered:
		return HandValue{}, NotWinningError{}
	case !b.hand.hasYaku:
		return HandValue{}, NoYakuError{}
	}

	best := b.hand
	yaku := slices.Clone(best.yaku)
	slices.SortFunc(yaku, func(a, b Yaku) int { return cmp.Compare(a.ID, b.ID) })
	fuDetails := slices.Clone(best.fuDetails.all())
	slices.SortStableFunc(fuDetails, func(a, b FuDetail) int { return cmp.Compare(b.Fu, a.Fu) })
	return HandValue{
		Value:     best.scored.value,
		Limit:     best.scored.limit,
		Payment:   best.scored.payment,
		Total:     best.scored.total,
		Yaku:      yaku,
		Dora:      best.scored.dora,
		FuDetails: fuDetails,
	}, nil
}

// WrongTileCountError reports concealed tiles that are not 13 less 3 for each meld.
type WrongTileCountError struct {
	Concealed int
	Melds     int
}

func (e WrongTileCountError) Error() string {
	return "the hand has " + strconv.Itoa(e.Concealed) + " concealed tiles with " + strconv.Itoa(e.Melds) +
		" melds, not 13 less 3 per meld"
}

// OpenHandRiichiError reports a riichi or double riichi with an open meld.
type OpenHandRiichiError struct{}

func (OpenHandRiichiError) Error() string {
	return "riichi needs a hand with no open meld"
}

// RinshanWithoutKanError reports a rinshan win with no kan among the melds.
type RinshanWithoutKanError struct{}

func (RinshanWithoutKanError) Error() string {
	return "a rinshan win needs a kan among the melds"
}

// IppatsuWithRinshanError reports ippatsu on a rinshan win: the kan ends the ippatsu.
type IppatsuWithRinshanError struct{}

func (IppatsuWithRinshanError) Error() string {
	return "ippatsu cannot come with a rinshan win, as the kan ends it"
}

// FirstTurnWithMeldError reports a first-turn win after a call or a kan.
type FirstTurnWithMeldError struct{}

func (FirstTurnWithMeldError) Error() string {
	return "a first-turn win cannot follow a call or a kan"
}

// FirstTurnSpecialWinError reports a first-turn win other than a ron or a tsumo.
type FirstTurnSpecialWinError struct{}

func (FirstTurnSpecialWinError) Error() string {
	return "a first-turn win must be a ron or a tsumo"
}

// FirstTurnWithRiichiError reports a first-turn win after a riichi.
type FirstTurnWithRiichiError struct{}

func (FirstTurnWithRiichiError) Error() string {
	return "a first-turn win cannot follow a riichi"
}

// FirstTurnDealerRonError reports a first-turn ron by the dealer, who discards first.
type FirstTurnDealerRonError struct{}

func (FirstTurnDealerRonError) Error() string {
	return "the dealer cannot win by ron on the first turn, as the dealer discards first"
}

// NotWinningError reports tiles that make no four sets and a pair, seven pairs or thirteen
// orphans.
type NotWinningError struct{}

func (NotWinningError) Error() string {
	return "the tiles do not make a winning hand"
}

// NoYakuError reports tiles that win with no reading that has a yaku.
type NoYakuError struct{}

func (NoYakuError) Error() string {
	return "the hand wins but has no yaku"
}
