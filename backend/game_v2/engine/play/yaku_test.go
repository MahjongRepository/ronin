package play_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

type yakuRow struct {
	yaku      play.YakuID
	id        int
	name      string
	hanOpen   int
	hanClosed int
	isYakuman bool
}

func TestAllYaku_ShouldMatchTheYakuTable(t *testing.T) {
	yakuTable := [...]yakuRow{
		{yaku: play.YakuTsumo, id: 0, name: "Menzen Tsumo", hanOpen: 0, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuRiichi, id: 1, name: "Riichi", hanOpen: 0, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuIppatsu, id: 3, name: "Ippatsu", hanOpen: 0, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuChankan, id: 4, name: "Chankan", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuRinshan, id: 5, name: "Rinshan Kaihou", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuHaitei, id: 6, name: "Haitei Raoyue", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuHoutei, id: 7, name: "Houtei Raoyui", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuDaburuRiichi, id: 8, name: "Double Riichi", hanOpen: 0, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuPinfu, id: 12, name: "Pinfu", hanOpen: 0, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuTanyao, id: 13, name: "Tanyao", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuIipeikou, id: 14, name: "Iipeiko", hanOpen: 0, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuHaku, id: 15, name: "Yakuhai (haku)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuHatsu, id: 16, name: "Yakuhai (hatsu)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuChun, id: 17, name: "Yakuhai (chun)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuSeatWindEast, id: 18, name: "Yakuhai (seat wind east)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuSeatWindSouth, id: 19, name: "Yakuhai (seat wind south)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuSeatWindWest, id: 20, name: "Yakuhai (seat wind west)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuSeatWindNorth, id: 21, name: "Yakuhai (seat wind north)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuRoundWindEast, id: 22, name: "Yakuhai (round wind east)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuRoundWindSouth, id: 23, name: "Yakuhai (round wind south)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuRoundWindWest, id: 24, name: "Yakuhai (round wind west)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuRoundWindNorth, id: 25, name: "Yakuhai (round wind north)", hanOpen: 1, hanClosed: 1, isYakuman: false},
		{yaku: play.YakuSanshoku, id: 26, name: "Sanshoku Doujun", hanOpen: 1, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuIttsu, id: 27, name: "Ittsu", hanOpen: 1, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuChantai, id: 28, name: "Chantai", hanOpen: 1, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuHonroutou, id: 29, name: "Honroutou", hanOpen: 2, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuToitoi, id: 30, name: "Toitoi", hanOpen: 2, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuSanankou, id: 31, name: "San Ankou", hanOpen: 2, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuSankantsu, id: 32, name: "San Kantsu", hanOpen: 2, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuSanshokuDoukou, id: 33, name: "Sanshoku Doukou", hanOpen: 2, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuChiitoitsu, id: 34, name: "Chiitoitsu", hanOpen: 0, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuShousangen, id: 35, name: "Shou Sangen", hanOpen: 2, hanClosed: 2, isYakuman: false},
		{yaku: play.YakuHonitsu, id: 36, name: "Honitsu", hanOpen: 2, hanClosed: 3, isYakuman: false},
		{yaku: play.YakuJunchan, id: 37, name: "Junchan", hanOpen: 2, hanClosed: 3, isYakuman: false},
		{yaku: play.YakuRyanpeikou, id: 38, name: "Ryanpeikou", hanOpen: 0, hanClosed: 3, isYakuman: false},
		{yaku: play.YakuChinitsu, id: 39, name: "Chinitsu", hanOpen: 5, hanClosed: 6, isYakuman: false},
		{yaku: play.YakuKokushiMusou, id: 100, name: "Kokushi Musou", hanOpen: 0, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuChuurenPoutou, id: 101, name: "Chuuren Poutou", hanOpen: 0, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuSuuankou, id: 102, name: "Suu Ankou", hanOpen: 0, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuDaisangen, id: 103, name: "Daisangen", hanOpen: 13, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuShousuushii, id: 104, name: "Shousuushii", hanOpen: 13, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuRyuuiisou, id: 105, name: "Ryuuiisou", hanOpen: 13, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuSuukantsu, id: 106, name: "Suu Kantsu", hanOpen: 13, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuTsuuiisou, id: 107, name: "Tsuu Iisou", hanOpen: 13, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuChinroutou, id: 108, name: "Chinroutou", hanOpen: 13, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuDaisuushii, id: 111, name: "Dai Suushii", hanOpen: 26, hanClosed: 26, isYakuman: true},
		{yaku: play.YakuDaburuKokushiMusou, id: 112, name: "Kokushi Musou Juusanmen Matchi", hanOpen: 0, hanClosed: 26, isYakuman: true},
		{yaku: play.YakuSuuankouTanki, id: 113, name: "Suu Ankou Tanki", hanOpen: 0, hanClosed: 26, isYakuman: true},
		{yaku: play.YakuDaburuChuurenPoutou, id: 114, name: "Junsei Chuuren Poutou", hanOpen: 0, hanClosed: 26, isYakuman: true},
		{yaku: play.YakuTenhou, id: 115, name: "Tenhou", hanOpen: 0, hanClosed: 13, isYakuman: true},
		{yaku: play.YakuChiihou, id: 116, name: "Chiihou", hanOpen: 0, hanClosed: 13, isYakuman: true},
	}

	all := play.AllYaku()
	if len(yakuTable) != len(all) {
		t.Fatalf("table holds %d yaku, AllYaku %d", len(yakuTable), len(all))
	}

	for i, row := range yakuTable {
		t.Run(row.name, func(t *testing.T) {
			yaku := all[i]
			if yaku != row.yaku {
				t.Errorf("AllYaku()[%d] = %d, want %s", i, yaku, row.name)
			}

			if int(yaku) != row.id {
				t.Errorf("id = %d, want %d", yaku, row.id)
			}

			if got := yaku.Name(); got != row.name {
				t.Errorf("yaku %d Name = %q, want %q", row.id, got, row.name)
			}

			hanOpen, isOpen := yaku.HanOpen()
			if hanOpen != row.hanOpen || isOpen != (row.hanOpen != 0) {
				t.Errorf("HanOpen = %d, %t, want %d", hanOpen, isOpen, row.hanOpen)
			}

			if got := yaku.HanClosed(); got != row.hanClosed {
				t.Errorf("HanClosed = %d, want %d", got, row.hanClosed)
			}

			if got := yaku.IsYakuman(); got != row.isYakuman {
				t.Errorf("IsYakuman = %t, want %t", got, row.isYakuman)
			}
		})
	}
}

func TestAllYaku_ShouldListEveryYakuOnceInIDOrder(t *testing.T) {
	all := play.AllYaku()
	for i := 1; i < len(all); i++ {
		if all[i-1] >= all[i] {
			t.Errorf("AllYaku()[%d] = %d is not below AllYaku()[%d] = %d", i-1, all[i-1], i, all[i])
		}
	}
}

func TestYakuIDIsDoubleYakuman_ShouldHoldOnlyForTheFourDoubleForms(t *testing.T) {
	var doubles []play.YakuID
	for _, yaku := range play.AllYaku() {
		if yaku.IsDoubleYakuman() {
			doubles = append(doubles, yaku)
		}
	}

	want := []play.YakuID{
		play.YakuDaisuushii,
		play.YakuDaburuKokushiMusou,
		play.YakuSuuankouTanki,
		play.YakuDaburuChuurenPoutou,
	}
	if !slices.Equal(doubles, want) {
		t.Errorf("double yakuman forms = %v, want %v", doubles, want)
	}
}
