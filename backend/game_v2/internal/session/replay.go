package session

import "github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"

func encodeReplay(records []wire.Map) ([]byte, error) {
	return wire.EncodeReplay(append([]wire.Map{wire.VersionRecord()}, records...))
}
