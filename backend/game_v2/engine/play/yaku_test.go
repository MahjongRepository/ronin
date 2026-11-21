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
		{play.YakuTsumo, 0, "Menzen Tsumo", 0, 1, false},
		{play.YakuRiichi, 1, "Riichi", 0, 1, false},
		{play.YakuIppatsu, 3, "Ippatsu", 0, 1, false},
		{play.YakuChankan, 4, "Chankan", 1, 1, false},
		{play.YakuRinshan, 5, "Rinshan Kaihou", 1, 1, false},
		{play.YakuHaitei, 6, "Haitei Raoyue", 1, 1, false},
		{play.YakuHoutei, 7, "Houtei Raoyui", 1, 1, false},
		{play.YakuDaburuRiichi, 8, "Double Riichi", 0, 2, false},
		{play.YakuPinfu, 12, "Pinfu", 0, 1, false},
		{play.YakuTanyao, 13, "Tanyao", 1, 1, false},
		{play.YakuIipeikou, 14, "Iipeiko", 0, 1, false},
		{play.YakuHaku, 15, "Yakuhai (haku)", 1, 1, false},
		{play.YakuHatsu, 16, "Yakuhai (hatsu)", 1, 1, false},
		{play.YakuChun, 17, "Yakuhai (chun)", 1, 1, false},
		{play.YakuSeatWindEast, 18, "Yakuhai (seat wind east)", 1, 1, false},
		{play.YakuSeatWindSouth, 19, "Yakuhai (seat wind south)", 1, 1, false},
		{play.YakuSeatWindWest, 20, "Yakuhai (seat wind west)", 1, 1, false},
		{play.YakuSeatWindNorth, 21, "Yakuhai (seat wind north)", 1, 1, false},
		{play.YakuRoundWindEast, 22, "Yakuhai (round wind east)", 1, 1, false},
		{play.YakuRoundWindSouth, 23, "Yakuhai (round wind south)", 1, 1, false},
		{play.YakuRoundWindWest, 24, "Yakuhai (round wind west)", 1, 1, false},
		{play.YakuRoundWindNorth, 25, "Yakuhai (round wind north)", 1, 1, false},
		{play.YakuSanshoku, 26, "Sanshoku Doujun", 1, 2, false},
		{play.YakuIttsu, 27, "Ittsu", 1, 2, false},
		{play.YakuChantai, 28, "Chantai", 1, 2, false},
		{play.YakuHonroutou, 29, "Honroutou", 2, 2, false},
		{play.YakuToitoi, 30, "Toitoi", 2, 2, false},
		{play.YakuSanankou, 31, "San Ankou", 2, 2, false},
		{play.YakuSankantsu, 32, "San Kantsu", 2, 2, false},
		{play.YakuSanshokuDoukou, 33, "Sanshoku Doukou", 2, 2, false},
		{play.YakuChiitoitsu, 34, "Chiitoitsu", 0, 2, false},
		{play.YakuShousangen, 35, "Shou Sangen", 2, 2, false},
		{play.YakuHonitsu, 36, "Honitsu", 2, 3, false},
		{play.YakuJunchan, 37, "Junchan", 2, 3, false},
		{play.YakuRyanpeikou, 38, "Ryanpeikou", 0, 3, false},
		{play.YakuChinitsu, 39, "Chinitsu", 5, 6, false},
		{play.YakuKokushiMusou, 100, "Kokushi Musou", 0, 13, true},
		{play.YakuChuurenPoutou, 101, "Chuuren Poutou", 0, 13, true},
		{play.YakuSuuankou, 102, "Suu Ankou", 0, 13, true},
		{play.YakuDaisangen, 103, "Daisangen", 13, 13, true},
		{play.YakuShousuushii, 104, "Shousuushii", 13, 13, true},
		{play.YakuRyuuiisou, 105, "Ryuuiisou", 13, 13, true},
		{play.YakuSuukantsu, 106, "Suu Kantsu", 13, 13, true},
		{play.YakuTsuuiisou, 107, "Tsuu Iisou", 13, 13, true},
		{play.YakuChinroutou, 108, "Chinroutou", 13, 13, true},
		{play.YakuDaisuushii, 111, "Dai Suushii", 26, 26, true},
		{play.YakuDaburuKokushiMusou, 112, "Kokushi Musou Juusanmen Matchi", 0, 26, true},
		{play.YakuSuuankouTanki, 113, "Suu Ankou Tanki", 0, 26, true},
		{play.YakuDaburuChuurenPoutou, 114, "Daburu Chuuren Poutou", 0, 26, true},
		{play.YakuTenhou, 115, "Tenhou", 0, 13, true},
		{play.YakuChiihou, 116, "Chiihou", 0, 13, true},
	}

	all := play.AllYaku()
	if len(yakuTable) != len(all) {
		t.Fatalf("table holds %d yaku, AllYaku %d", len(yakuTable), len(all))
	}

	for i, row := range yakuTable {
		yaku := all[i]
		if yaku != row.yaku {
			t.Errorf("AllYaku()[%d] = %d, want %s", i, yaku, row.name)
		}
		if int(yaku) != row.id {
			t.Errorf("%s id = %d, want %d", row.name, yaku, row.id)
		}
		if got := yaku.Name(); got != row.name {
			t.Errorf("yaku %d Name = %q, want %q", row.id, got, row.name)
		}
		hanOpen, isOpen := yaku.HanOpen()
		if hanOpen != row.hanOpen || isOpen != (row.hanOpen != 0) {
			t.Errorf("%s HanOpen = %d, %t, want %d", row.name, hanOpen, isOpen, row.hanOpen)
		}
		if got := yaku.HanClosed(); got != row.hanClosed {
			t.Errorf("%s HanClosed = %d, want %d", row.name, got, row.hanClosed)
		}
		if got := yaku.IsYakuman(); got != row.isYakuman {
			t.Errorf("%s IsYakuman = %t, want %t", row.name, got, row.isYakuman)
		}
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
