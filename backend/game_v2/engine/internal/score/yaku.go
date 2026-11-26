package score

import (
	"math/bits"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	valuedKinds      = 5
	singleYakumanHan = 13
	sanankouTriplets = 3
	suuankouTriplets = 4
	sankantsuKans    = 3
	suukantsuKans    = 4
)

// Yaku is a yaku a hand scored, with the han it scored.
type Yaku struct {
	ID  play.YakuID
	Han int
}

type yakuInput struct {
	counts    [tile.KindCount]uint8
	kinds     uint64
	win       tile.Kind
	hasMelds  bool
	open      bool
	situation Situation
	rules     Rules
}

type yakuList []Yaku

func (in yakuInput) han(id play.YakuID) (int, bool) {
	if id == play.YakuTanyao && in.open && !in.rules.OpenTanyao {
		return 0, false
	}

	hanOpen, hasOpen := id.HanOpen()
	switch {
	case in.open && !hasOpen:
		return 0, false
	case !in.rules.DoubleYakuman && id.IsDoubleYakuman():
		return singleYakumanHan, true
	case in.open:
		return hanOpen, true
	default:
		return id.HanClosed(), true
	}
}

func (in yakuInput) add(list yakuList, id play.YakuID) yakuList {
	han, ok := in.han(id)
	if !ok {
		return list
	}

	return append(list, Yaku{ID: id, Han: han})
}

func (in yakuInput) evaluate(reading hand.Reading, winBlock hand.WinBlock) yakuList {
	list := in.addWinConditionYaku(nil, reading, winBlock)
	list = in.addSuitAndTerminalYaku(list)
	if reading.Sequences != 0 {
		list = in.addChiYaku(list, reading)
	}

	if reading.Triplets != 0 {
		list = in.addPonYaku(list, reading, winBlock)
	}

	return list
}

func (in yakuInput) evaluateKokushi() yakuList {
	kokushi := play.YakuKokushiMusou
	if in.winTileCount() == 2 {
		kokushi = play.YakuDaburuKokushiMusou
	}

	list := in.add(nil, kokushi)
	return in.addFirstTurnYaku(list)
}

func (in yakuInput) valuedKinds() [valuedKinds]tile.Kind {
	return [valuedKinds]tile.Kind{
		tile.KindHaku, tile.KindHatsu, tile.KindChun, in.situation.SeatWind.Kind(), in.situation.RoundWind.Kind(),
	}
}

func (in yakuInput) winTileCount() int {
	return int(in.counts[in.win])
}

func (in yakuInput) hasHonors() bool {
	return in.kinds&tile.HonorMask != 0
}

func (in yakuInput) suitCount() int {
	suits := 0
	for _, mask := range tile.SuitMasks() {
		if in.kinds&mask != 0 {
			suits++
		}
	}

	return suits
}

func (in yakuInput) isChinitsu() bool {
	return in.suitCount() == 1 && !in.hasHonors()
}

func (in yakuInput) isHonitsu() bool {
	return in.suitCount() == 1 && in.hasHonors()
}

func (in yakuInput) isPinfu(reading hand.Reading, winBlock hand.WinBlock) bool {
	set, isSet := winBlock.Set()
	if reading.SevenPairs || !isSet || set.Shape != hand.Sequence {
		return false
	}

	_, hasPairFu := valuedPairFu(reading.Pair, in.valuedKinds(), in.rules.FuForDoubleWindPair)
	_, hasWaitFu := chiWaitFu(set.Kind, in.win)
	hasTsumoFu := in.situation.Win.IsTsumo() && in.rules.FuForPinfuTsumo
	return reading.Triplets == 0 && !hasPairFu && !hasWaitFu && !hasTsumoFu
}

func (in yakuInput) addWinConditionYaku(list yakuList, reading hand.Reading, winBlock hand.WinBlock) yakuList {
	situation := in.situation
	if situation.Win.IsTsumo() {
		list = in.add(list, play.YakuTsumo)
	}

	if in.isPinfu(reading, winBlock) {
		list = in.add(list, play.YakuPinfu)
	}

	if reading.SevenPairs {
		list = in.add(list, play.YakuChiitoitsu)
	}

	if isTanyao(in.kinds) {
		list = in.add(list, play.YakuTanyao)
	}

	if riichi := situation.Riichi; riichi.OK {
		list = in.addRiichiYaku(list, riichi.Value)
	}

	switch situation.Win {
	case WinRon, WinTsumo:
	case WinRinshan:
		list = in.add(list, play.YakuRinshan)
	case WinChankan:
		list = in.add(list, play.YakuChankan)
	case WinHaitei:
		list = in.add(list, play.YakuHaitei)
	case WinHoutei:
		list = in.add(list, play.YakuHoutei)
	}

	return in.addFirstTurnYaku(list)
}

func (in yakuInput) addRiichiYaku(list yakuList, riichi play.Riichi) yakuList {
	if riichi.Double {
		list = in.add(list, play.YakuDaburuRiichi)
	} else {
		list = in.add(list, play.YakuRiichi)
	}

	if riichi.Ippatsu {
		list = in.add(list, play.YakuIppatsu)
	}

	return list
}

func (in yakuInput) addFirstTurnYaku(list yakuList) yakuList {
	situation := in.situation
	switch {
	case !situation.FirstTurn || !situation.Win.IsTsumo():
		return list
	case situation.IsDealer():
		return in.add(list, play.YakuTenhou)
	default:
		return in.add(list, play.YakuChiihou)
	}
}

func (in yakuInput) addSuitAndTerminalYaku(list yakuList) yakuList {
	switch {
	case in.isChinitsu():
		list = in.add(list, play.YakuChinitsu)
	case in.isHonitsu():
		list = in.add(list, play.YakuHonitsu)
	}

	if isTsuuiisou(in.kinds) {
		list = in.add(list, play.YakuTsuuiisou)
	}

	if isHonroutou(in.kinds) {
		list = in.add(list, play.YakuHonroutou)
	}

	if isChinroutou(in.kinds) {
		list = in.add(list, play.YakuChinroutou)
	}

	if isRyuuiisou(in.kinds) {
		list = in.add(list, play.YakuRyuuiisou)
	}

	if in.hasMelds || !in.isChinitsu() || !hasChuurenPoutouRanks(in.counts) {
		return list
	}

	if count := in.winTileCount(); count == 2 || count == 4 {
		return in.add(list, play.YakuDaburuChuurenPoutou)
	}

	return in.add(list, play.YakuChuurenPoutou)
}

func (in yakuInput) addChiYaku(list yakuList, reading hand.Reading) yakuList {
	switch {
	case isChantaShape(reading) && in.hasHonors():
		list = in.add(list, play.YakuChantai)
	case isChantaShape(reading):
		list = in.add(list, play.YakuJunchan)
	}

	if isIttsu(reading.Sequences) {
		list = in.add(list, play.YakuIttsu)
	}

	switch reading.IdenticalSequencePairs {
	case 0:
	case 1:
		list = in.add(list, play.YakuIipeikou)
	default:
		list = in.add(list, play.YakuRyanpeikou)
	}

	if isSanshoku(reading.Sequences) {
		list = in.add(list, play.YakuSanshoku)
	}

	return list
}

func (in yakuInput) addPonYaku(list yakuList, reading hand.Reading, winBlock hand.WinBlock) yakuList {
	closedTriplets := countClosedTriplets(reading, winBlock, in.situation.Win.IsTsumo())
	kans := bits.OnesCount64(reading.Kans)

	if isToitoi(reading.Triplets) {
		list = in.add(list, play.YakuToitoi)
	}

	if closedTriplets == sanankouTriplets {
		list = in.add(list, play.YakuSanankou)
	}

	if isSanshokuDoukou(reading.Triplets) {
		list = in.add(list, play.YakuSanshokuDoukou)
	}

	if in.hasHonors() {
		list = in.addHonorYaku(list)
	}

	if closedTriplets == suuankouTriplets {
		if _, isSet := winBlock.Set(); isSet {
			list = in.add(list, play.YakuSuuankou)
		} else {
			list = in.add(list, play.YakuSuuankouTanki)
		}
	}

	switch kans {
	case sankantsuKans:
		list = in.add(list, play.YakuSankantsu)
	case suukantsuKans:
		list = in.add(list, play.YakuSuukantsu)
	}

	return list
}

func (in yakuInput) addHonorYaku(list yakuList) yakuList {
	if isShousangen(in.counts) {
		list = in.add(list, play.YakuShousangen)
	}

	if hasHonorSet(in.counts, tile.KindHaku) {
		list = in.add(list, play.YakuHaku)
	}

	if hasHonorSet(in.counts, tile.KindHatsu) {
		list = in.add(list, play.YakuHatsu)
	}

	if hasHonorSet(in.counts, tile.KindChun) {
		list = in.add(list, play.YakuChun)
	}

	for _, seat := range seatWindYaku {
		if isSeatWind(in.counts, seat.wind, in.situation.SeatWind) {
			list = in.add(list, seat.yaku)
		}
	}

	for _, round := range roundWindYaku {
		if isRoundWind(in.counts, round.wind, in.situation.RoundWind) {
			list = in.add(list, round.yaku)
		}
	}

	if isDaisangen(in.counts) {
		list = in.add(list, play.YakuDaisangen)
	}

	if isShousuushii(in.counts) {
		list = in.add(list, play.YakuShousuushii)
	}

	if isDaisuushii(in.counts) {
		list = in.add(list, play.YakuDaisuushii)
	}

	return list
}
