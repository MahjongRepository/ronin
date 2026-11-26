package tenhou_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou"
)

func TestYakuID_ShouldGiveEveryYakuItsTenhouID(t *testing.T) {
	ids := [...]struct {
		yaku play.YakuID
		id   int
	}{
		{play.YakuTsumo, 0},
		{play.YakuRiichi, 1},
		{play.YakuIppatsu, 2},
		{play.YakuChankan, 3},
		{play.YakuRinshan, 4},
		{play.YakuHaitei, 5},
		{play.YakuHoutei, 6},
		{play.YakuDaburuRiichi, 21},
		{play.YakuPinfu, 7},
		{play.YakuTanyao, 8},
		{play.YakuIipeikou, 9},
		{play.YakuHaku, 18},
		{play.YakuHatsu, 19},
		{play.YakuChun, 20},
		{play.YakuSeatWindEast, 10},
		{play.YakuSeatWindSouth, 11},
		{play.YakuSeatWindWest, 12},
		{play.YakuSeatWindNorth, 13},
		{play.YakuRoundWindEast, 14},
		{play.YakuRoundWindSouth, 15},
		{play.YakuRoundWindWest, 16},
		{play.YakuRoundWindNorth, 17},
		{play.YakuSanshoku, 25},
		{play.YakuIttsu, 24},
		{play.YakuChantai, 23},
		{play.YakuHonroutou, 31},
		{play.YakuToitoi, 28},
		{play.YakuSanankou, 29},
		{play.YakuSankantsu, 27},
		{play.YakuSanshokuDoukou, 26},
		{play.YakuChiitoitsu, 22},
		{play.YakuShousangen, 30},
		{play.YakuHonitsu, 34},
		{play.YakuJunchan, 33},
		{play.YakuRyanpeikou, 32},
		{play.YakuChinitsu, 35},
		{play.YakuKokushiMusou, 47},
		{play.YakuChuurenPoutou, 45},
		{play.YakuSuuankou, 40},
		{play.YakuDaisangen, 39},
		{play.YakuShousuushii, 50},
		{play.YakuRyuuiisou, 43},
		{play.YakuSuukantsu, 51},
		{play.YakuTsuuiisou, 42},
		{play.YakuChinroutou, 44},
		{play.YakuDaisuushii, 49},
		{play.YakuDaburuKokushiMusou, 48},
		{play.YakuSuuankouTanki, 41},
		{play.YakuDaburuChuurenPoutou, 46},
		{play.YakuTenhou, 37},
		{play.YakuChiihou, 38},
	}
	if len(ids) != play.YakuCount {
		t.Fatalf("%d rows, want %d", len(ids), play.YakuCount)
	}

	for _, row := range ids {
		if got, ok := tenhou.YakuID(row.yaku); !ok || got != row.id {
			t.Errorf("YakuID(%s) = %d, %t, want %d", row.yaku.Name(), got, ok, row.id)
		}
	}

	if _, ok := tenhou.YakuID(play.YakuID(99)); ok {
		t.Error("YakuID(99) found an id")
	}
}

func TestLimitCode_ShouldCountFromOneForMangan(t *testing.T) {
	for code, limit := range []play.Limit{
		play.LimitMangan, play.LimitHaneman, play.LimitBaiman, play.LimitSanbaiman, play.LimitYakuman,
	} {
		if got := tenhou.LimitCode(limit); got != code+1 {
			t.Errorf("LimitCode(%s) = %d, want %d", limit, got, code+1)
		}
	}
}
