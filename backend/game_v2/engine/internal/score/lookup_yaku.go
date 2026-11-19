package score

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type windYaku struct {
	wind tile.Kind
	yaku play.YakuID
}

var seatWindYaku = [windCount]windYaku{
	{tile.KindEast, play.YakuSeatWindEast},
	{tile.KindSouth, play.YakuSeatWindSouth},
	{tile.KindWest, play.YakuSeatWindWest},
	{tile.KindNorth, play.YakuSeatWindNorth},
}

var roundWindYaku = [windCount]windYaku{
	{tile.KindEast, play.YakuRoundWindEast},
	{tile.KindSouth, play.YakuRoundWindSouth},
	{tile.KindWest, play.YakuRoundWindWest},
	{tile.KindNorth, play.YakuRoundWindNorth},
}
