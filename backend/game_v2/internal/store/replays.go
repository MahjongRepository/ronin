package store

import (
	"bytes"
	"compress/gzip"
	"crypto/rand"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path"
)

const (
	replayDirMode     = 0o700
	replayFileMode    = 0o600
	minGameIDLength   = 4
	maxGameIDLength   = 50
	replayTempPrefix  = ".replay_"
	replayTempSuffix  = ".tmp"
	shardPrefixLength = 2
)

// ReplayFileSuffix ends the name of every stored replay file.
const ReplayFileSuffix = ".msgpack.gz"

// MaxReplayFileSize is the largest stored replay file Replays.Read returns, in bytes.
const MaxReplayFileSize = 1 << 20

// The reasons Replays refuses a replay.
var (
	ErrInvalidGameID  = errors.New("game id cannot name a stored replay")
	ErrReplayTooLarge = errors.New("stored replay is over the size cap")
)

// Replays stores gzip-compressed replay files under one directory, each at
// `aa/bb/<game id>.msgpack.gz` for a game id starting `aabb`: owner-only directories, owner-only
// files, each written whole to a temporary file, synced and renamed into place. Every path is
// opened through an os.Root, so neither a game id nor a symbolic link reaches outside the
// directory. The zero value is not usable; build one with NewReplays.
type Replays struct {
	dir string
}

// NewReplays returns the replay store over dir, created on the first save.
func NewReplays(dir string) Replays {
	return Replays{dir: dir}
}

// IsValidGameID reports whether a game id can name a stored replay: 4 to 50 ASCII letters, digits,
// hyphens and underscores.
func IsValidGameID(id string) bool {
	if len(id) < minGameIDLength || len(id) > maxGameIDLength {
		return false
	}
	for _, c := range []byte(id) {
		isWordByte := c == '-' || c == '_' || ('0' <= c && c <= '9') || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z')
		if !isWordByte {
			return false
		}
	}
	return true
}

// Save compresses a game's encoded replay and stores it, replacing any replay already stored for
// it. It returns ErrInvalidGameID for an id IsValidGameID refuses.
func (r Replays) Save(gameID string, content []byte) (err error) {
	if !IsValidGameID(gameID) {
		return fmt.Errorf("save replay %q: %w", gameID, ErrInvalidGameID)
	}

	compressed, err := compressReplay(content)
	if err != nil {
		return fmt.Errorf("save replay %s: %w", gameID, err)
	}

	err = os.MkdirAll(r.dir, replayDirMode)
	if err != nil {
		return fmt.Errorf("save replay %s: %w", gameID, err)
	}

	root, err := os.OpenRoot(r.dir)
	if err != nil {
		return fmt.Errorf("save replay %s: %w", gameID, err)
	}
	defer func() { err = errors.Join(err, root.Close()) }()

	err = writeReplay(root, gameID, compressed)
	if err != nil {
		return fmt.Errorf("save replay %s: %w", gameID, err)
	}
	return nil
}

// Read returns a stored replay's gzip-compressed bytes. It returns ErrInvalidGameID for an id
// IsValidGameID refuses, ErrReplayTooLarge for a file over MaxReplayFileSize, and an error matching
// fs.ErrNotExist when no replay is stored for the game.
func (r Replays) Read(gameID string) (data []byte, err error) {
	if !IsValidGameID(gameID) {
		return nil, fmt.Errorf("read replay %q: %w", gameID, ErrInvalidGameID)
	}

	root, err := os.OpenRoot(r.dir)
	if err != nil {
		return nil, fmt.Errorf("read replay %s: %w", gameID, err)
	}
	defer func() { err = errors.Join(err, root.Close()) }()

	file, err := root.Open(ReplayPath(gameID))
	if err != nil {
		return nil, fmt.Errorf("read replay %s: %w", gameID, err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()

	data, err = io.ReadAll(io.LimitReader(file, MaxReplayFileSize+1))
	if err != nil {
		return nil, fmt.Errorf("read replay %s: %w", gameID, err)
	}
	if len(data) > MaxReplayFileSize {
		return nil, fmt.Errorf("read replay %s: %w", gameID, ErrReplayTooLarge)
	}
	return data, nil
}

// DecompressReplay returns the content of a replay file Read returned, reading at most limit+1
// bytes of it, so a caller that refuses content over limit sees that it is; an error for data
// that is not gzip.
func DecompressReplay(compressed []byte, limit int) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		return nil, fmt.Errorf("decompress replay: %w", err)
	}
	content, err := io.ReadAll(io.LimitReader(reader, int64(limit)+1))
	if err != nil {
		return nil, fmt.Errorf("decompress replay: %w", err)
	}
	err = reader.Close()
	if err != nil {
		return nil, fmt.Errorf("decompress replay: %w", err)
	}
	return content, nil
}

func shardDir(gameID string) string {
	return path.Join(gameID[:shardPrefixLength], gameID[shardPrefixLength:2*shardPrefixLength])
}

// ReplayPath returns where Replays stores a game's replay, relative to its directory, for a game id
// IsValidGameID accepts: `aa/bb/<game id>.msgpack.gz` for an id starting `aabb`.
func ReplayPath(gameID string) string {
	return path.Join(shardDir(gameID), gameID+ReplayFileSuffix)
}

func compressReplay(content []byte) ([]byte, error) {
	var compressed bytes.Buffer
	writer, err := gzip.NewWriterLevel(&compressed, gzip.BestCompression)
	if err != nil {
		return nil, err
	}

	_, err = writer.Write(content)
	if err != nil {
		return nil, err
	}

	err = writer.Close()
	if err != nil {
		return nil, err
	}
	return compressed.Bytes(), nil
}

func writeReplay(root *os.Root, gameID string, compressed []byte) error {
	shard := shardDir(gameID)
	err := root.MkdirAll(shard, replayDirMode)
	if err != nil {
		return err
	}

	for _, dir := range []string{".", path.Dir(shard), shard} {
		err = root.Chmod(dir, replayDirMode)
		if err != nil {
			return err
		}
	}

	temp := path.Join(shard, replayTempPrefix+rand.Text()+replayTempSuffix)
	err = writeSynced(root, temp, compressed)
	if err == nil {
		err = root.Rename(temp, ReplayPath(gameID))
	}
	if err != nil {
		removeErr := root.Remove(temp)
		if errors.Is(removeErr, fs.ErrNotExist) {
			removeErr = nil
		}
		return errors.Join(err, removeErr)
	}
	return nil
}

func writeSynced(root *os.Root, name string, content []byte) error {
	file, err := root.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, replayFileMode)
	if err != nil {
		return err
	}

	_, err = file.Write(content)
	if err == nil {
		err = file.Sync()
	}
	if err == nil {
		err = file.Chmod(replayFileMode)
	}
	return errors.Join(err, file.Close())
}
