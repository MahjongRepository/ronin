package score

import (
	"math/bits"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// FuReason is what a reading scores fu for. FuBase is 20 for an open hand or a tsumo, 30 for a
// closed ron and 25 for chiitoitsu; FuValuedPair is a pair of dragons, the seat wind or the round
// wind, FuDoubleValuedPair a pair valued twice, such as East when East is both the seat and the
// round wind; FuHandWithoutFu is an open hand won by ron with no other fu.
type FuReason uint8

// The fu reasons.
const (
	FuBase FuReason = iota
	FuPenchan
	FuKanchan
	FuValuedPair
	FuDoubleValuedPair
	FuPairWait
	FuTsumo
	FuHandWithoutFu
	FuClosedPon
	FuOpenPon
	FuClosedTerminalPon
	FuOpenTerminalPon
	FuClosedKan
	FuOpenKan
	FuClosedTerminalKan
	FuOpenTerminalKan
)

// FuDetail is the fu a reading scores for one reason, not rounded.
type FuDetail struct {
	Fu     int
	Reason FuReason
}

const (
	maxFuDetails      = 8
	chiitoitsuFu      = 25
	openOrTsumoBaseFu = 20
	closedRonBaseFu   = 30
	waitFu            = 2
	fuRounding        = 10
	lastSequenceStart = 6
)

type fuDetails struct {
	details [maxFuDetails]FuDetail
	len     int
}

func (d *fuDetails) push(detail FuDetail) {
	d.details[d.len] = detail
	d.len++
}

func (d fuDetails) all() []FuDetail {
	return d.details[:d.len]
}

func (d fuDetails) total() int {
	total := 0
	for _, detail := range d.all() {
		total += detail.Fu
	}
	return total
}

func ponOrKanFu(terminalOrHonor, isKan, isOpen bool) FuDetail {
	simple, terminal := FuDetail{4, FuClosedPon}, FuDetail{8, FuClosedTerminalPon}
	switch {
	case isKan && isOpen:
		simple, terminal = FuDetail{8, FuOpenKan}, FuDetail{16, FuOpenTerminalKan}
	case isKan:
		simple, terminal = FuDetail{16, FuClosedKan}, FuDetail{32, FuClosedTerminalKan}
	case isOpen:
		simple, terminal = FuDetail{2, FuOpenPon}, FuDetail{4, FuOpenTerminalPon}
	}
	if terminalOrHonor {
		return terminal
	}
	return simple
}

func chiWaitFu(start, win tile.Kind) (FuDetail, bool) {
	middle, last := start+1, start+2
	startRank := start.Simplify()
	isPenchan := (startRank == 0 && win == last) || (startRank == lastSequenceStart && win == start)
	switch {
	case isPenchan:
		return FuDetail{Fu: waitFu, Reason: FuPenchan}, true
	case win == middle:
		return FuDetail{Fu: waitFu, Reason: FuKanchan}, true
	default:
		return FuDetail{}, false
	}
}

func valuedPairFu(pair tile.Kind, valued [valuedKinds]tile.Kind) (FuDetail, bool) {
	listed := 0
	for _, kind := range valued {
		if kind == pair {
			listed++
		}
	}
	switch listed {
	case 0:
		return FuDetail{}, false
	case 1:
		return FuDetail{Fu: 2, Reason: FuValuedPair}, true
	default:
		return FuDetail{Fu: 4, Reason: FuDoubleValuedPair}, true
	}
}

type fuInput struct {
	reading  hand.Reading
	winBlock hand.WinBlock
	win      tile.Kind
	tsumo    bool
	rules    Rules
	valued   [valuedKinds]tile.Kind
	open     bool
}

func calculateFu(in fuInput) (fuDetails, int) {
	var details fuDetails
	if in.reading.SevenPairs {
		details.push(FuDetail{Fu: chiitoitsuFu, Reason: FuBase})
		return details, chiitoitsuFu
	}

	set, isSet := in.winBlock.Set()
	if isSet && set.Shape == hand.Sequence {
		if detail, ok := chiWaitFu(set.Kind, in.win); ok {
			details.push(detail)
		}
	}
	if detail, ok := valuedPairFu(in.reading.Pair, in.valued); ok {
		details.push(detail)
	}
	if !isSet {
		details.push(FuDetail{Fu: waitFu, Reason: FuPairWait})
	}

	for remaining := in.reading.Triplets; remaining != 0; remaining &= remaining - 1 {
		kind := tile.Kind(bits.TrailingZeros64(remaining))
		bit := uint64(1) << kind
		isRonOnThisSet := !in.tsumo && isSet && set == hand.Set{Shape: hand.Triplet, Kind: kind}
		details.push(ponOrKanFu(
			kind.IsTerminalOrHonor(),
			in.reading.Kans&bit != 0,
			in.reading.OpenTriplets&bit != 0 || isRonOnThisSet,
		))
	}

	if in.tsumo && (in.open || details.len > 0 || in.rules.FuForPinfuTsumo) {
		details.push(FuDetail{Fu: waitFu, Reason: FuTsumo})
	}
	if in.open && !in.tsumo && details.len == 0 && in.rules.FuForOpenPinfu {
		details.push(FuDetail{Fu: waitFu, Reason: FuHandWithoutFu})
	}

	base := closedRonBaseFu
	if in.open || in.tsumo {
		base = openOrTsumoBaseFu
	}
	details.push(FuDetail{Fu: base, Reason: FuBase})
	return details, nextMultipleOf(details.total(), fuRounding)
}

func nextMultipleOf(n, multiple int) int {
	return (n + multiple - 1) / multiple * multiple
}
