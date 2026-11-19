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
	tenhouID  int
}

func TestAllYaku_ShouldMatchTheYakuTable(t *testing.T) {
	yakuTable := [...]yakuRow{
		{play.YakuTsumo, 0, "Menzen Tsumo", 0, 1, false, 0},
		{play.YakuRiichi, 1, "Riichi", 0, 1, false, 1},
		{play.YakuIppatsu, 3, "Ippatsu", 0, 1, false, 2},
		{play.YakuChankan, 4, "Chankan", 1, 1, false, 3},
		{play.YakuRinshan, 5, "Rinshan Kaihou", 1, 1, false, 4},
		{play.YakuHaitei, 6, "Haitei Raoyue", 1, 1, false, 5},
		{play.YakuHoutei, 7, "Houtei Raoyui", 1, 1, false, 6},
		{play.YakuDaburuRiichi, 8, "Double Riichi", 0, 2, false, 21},
		{play.YakuPinfu, 12, "Pinfu", 0, 1, false, 7},
		{play.YakuTanyao, 13, "Tanyao", 1, 1, false, 8},
		{play.YakuIipeikou, 14, "Iipeiko", 0, 1, false, 9},
		{play.YakuHaku, 15, "Yakuhai (haku)", 1, 1, false, 18},
		{play.YakuHatsu, 16, "Yakuhai (hatsu)", 1, 1, false, 19},
		{play.YakuChun, 17, "Yakuhai (chun)", 1, 1, false, 20},
		{play.YakuSeatWindEast, 18, "Yakuhai (seat wind east)", 1, 1, false, 10},
		{play.YakuSeatWindSouth, 19, "Yakuhai (seat wind south)", 1, 1, false, 11},
		{play.YakuSeatWindWest, 20, "Yakuhai (seat wind west)", 1, 1, false, 12},
		{play.YakuSeatWindNorth, 21, "Yakuhai (seat wind north)", 1, 1, false, 13},
		{play.YakuRoundWindEast, 22, "Yakuhai (round wind east)", 1, 1, false, 14},
		{play.YakuRoundWindSouth, 23, "Yakuhai (round wind south)", 1, 1, false, 15},
		{play.YakuRoundWindWest, 24, "Yakuhai (round wind west)", 1, 1, false, 16},
		{play.YakuRoundWindNorth, 25, "Yakuhai (round wind north)", 1, 1, false, 17},
		{play.YakuSanshoku, 26, "Sanshoku Doujun", 1, 2, false, 25},
		{play.YakuIttsu, 27, "Ittsu", 1, 2, false, 24},
		{play.YakuChantai, 28, "Chantai", 1, 2, false, 23},
		{play.YakuHonroutou, 29, "Honroutou", 2, 2, false, 31},
		{play.YakuToitoi, 30, "Toitoi", 2, 2, false, 28},
		{play.YakuSanankou, 31, "San Ankou", 2, 2, false, 29},
		{play.YakuSankantsu, 32, "San Kantsu", 2, 2, false, 27},
		{play.YakuSanshokuDoukou, 33, "Sanshoku Doukou", 2, 2, false, 26},
		{play.YakuChiitoitsu, 34, "Chiitoitsu", 0, 2, false, 22},
		{play.YakuShousangen, 35, "Shou Sangen", 2, 2, false, 30},
		{play.YakuHonitsu, 36, "Honitsu", 2, 3, false, 34},
		{play.YakuJunchan, 37, "Junchan", 2, 3, false, 33},
		{play.YakuRyanpeikou, 38, "Ryanpeikou", 0, 3, false, 32},
		{play.YakuChinitsu, 39, "Chinitsu", 5, 6, false, 35},
		{play.YakuKokushiMusou, 100, "Kokushi Musou", 0, 13, true, 47},
		{play.YakuChuurenPoutou, 101, "Chuuren Poutou", 0, 13, true, 45},
		{play.YakuSuuankou, 102, "Suu Ankou", 0, 13, true, 40},
		{play.YakuDaisangen, 103, "Daisangen", 13, 13, true, 39},
		{play.YakuShousuushii, 104, "Shousuushii", 13, 13, true, 50},
		{play.YakuRyuuiisou, 105, "Ryuuiisou", 13, 13, true, 43},
		{play.YakuSuukantsu, 106, "Suu Kantsu", 13, 13, true, 51},
		{play.YakuTsuuiisou, 107, "Tsuu Iisou", 13, 13, true, 42},
		{play.YakuChinroutou, 108, "Chinroutou", 13, 13, true, 44},
		{play.YakuDaisuushii, 111, "Dai Suushii", 26, 26, true, 49},
		{play.YakuDaburuKokushiMusou, 112, "Kokushi Musou Juusanmen Matchi", 0, 26, true, 48},
		{play.YakuSuuankouTanki, 113, "Suu Ankou Tanki", 0, 26, true, 41},
		{play.YakuDaburuChuurenPoutou, 114, "Daburu Chuuren Poutou", 0, 26, true, 46},
		{play.YakuTenhou, 115, "Tenhou", 0, 13, true, 37},
		{play.YakuChiihou, 116, "Chiihou", 0, 13, true, 38},
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
		if got := yaku.TenhouID(); got != row.tenhouID {
			t.Errorf("%s TenhouID = %d, want %d", row.name, got, row.tenhouID)
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

func TestDoraKinds_ShouldTakeTenhouIDs52To54PastEveryYaku(t *testing.T) {
	kinds := play.AllDoraKinds()
	var ids [3]int
	var names [3]string
	for i, kind := range kinds {
		ids[i] = kind.TenhouID()
		names[i] = kind.Name()
		if back, ok := play.DoraKindFromTenhouID(kind.TenhouID()); !ok || back != kind {
			t.Errorf("DoraKindFromTenhouID(%d) = %d, %t, want %d", kind.TenhouID(), back, ok, kind)
		}
	}
	if ids != [3]int{52, 53, 54} {
		t.Errorf("TenhouIDs = %v, want [52 53 54]", ids)
	}
	if names != [3]string{"Dora", "Ura Dora", "Aka Dora"} {
		t.Errorf("Names = %q", names)
	}

	for _, id := range []int{51, 55} {
		if _, ok := play.DoraKindFromTenhouID(id); ok {
			t.Errorf("DoraKindFromTenhouID(%d) found a kind", id)
		}
	}
	for _, yaku := range play.AllYaku() {
		if _, ok := play.DoraKindFromTenhouID(yaku.TenhouID()); ok {
			t.Errorf("%s TenhouID %d names a dora kind", yaku.Name(), yaku.TenhouID())
		}
	}
}

func TestDoraKindName_WhenKindIsUnknown_ShouldBeEmpty(t *testing.T) {
	if got := play.DoraKind(3).Name(); got != "" {
		t.Errorf("Name = %q, want empty", got)
	}
}
