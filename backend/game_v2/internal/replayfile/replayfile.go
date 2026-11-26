package replayfile

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

const Suffix = ".msgpack.gz"

const MaxFileSize = 1 << 20

var (
	ErrInvalidGameID = errors.New("game id cannot name a stored replay")
	ErrTooLarge      = errors.New("stored replay is over the size cap")
)

type Dir struct {
	dir        string
	idleWriter chan *gzip.Writer
}

// New returns the replay store over dir, created on the first save.
func New(dir string) Dir {
	return Dir{dir: dir, idleWriter: make(chan *gzip.Writer, 1)}
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
func (r Dir) Save(gameID string, content []byte) (err error) {
	if !IsValidGameID(gameID) {
		return fmt.Errorf("save replay %q: %w", gameID, ErrInvalidGameID)
	}

	compressed, err := r.compressReplay(content)
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

func (r Dir) Read(gameID string) (data []byte, err error) {
	if !IsValidGameID(gameID) {
		return nil, fmt.Errorf("read replay %q: %w", gameID, ErrInvalidGameID)
	}

	root, err := os.OpenRoot(r.dir)
	if err != nil {
		return nil, fmt.Errorf("read replay %s: %w", gameID, err)
	}
	defer func() { err = errors.Join(err, root.Close()) }()

	file, err := root.Open(Path(gameID))
	if err != nil {
		return nil, fmt.Errorf("read replay %s: %w", gameID, err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()

	data, err = io.ReadAll(io.LimitReader(file, MaxFileSize+1))
	if err != nil {
		return nil, fmt.Errorf("read replay %s: %w", gameID, err)
	}

	if len(data) > MaxFileSize {
		return nil, fmt.Errorf("read replay %s: %w", gameID, ErrTooLarge)
	}

	return data, nil
}

func Decompress(compressed []byte, limit int) ([]byte, error) {
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

// Path returns where Dir stores a game's replay, relative to its directory, for a game id
// IsValidGameID accepts: `aa/bb/<game id>.msgpack.gz` for an id starting `aabb`.
func Path(gameID string) string {
	return path.Join(shardDir(gameID), gameID+Suffix)
}

func (r Dir) compressReplay(content []byte) ([]byte, error) {
	var compressed bytes.Buffer
	writer, err := r.takeWriter(&compressed)
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

	writer.Reset(io.Discard)
	select {
	case r.idleWriter <- writer:
	default:
	}

	return compressed.Bytes(), nil
}

func (r Dir) takeWriter(output io.Writer) (*gzip.Writer, error) {
	select {
	case writer := <-r.idleWriter:
		writer.Reset(output)
		return writer, nil
	default:
		return gzip.NewWriterLevel(output, gzip.BestCompression)
	}
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
		err = root.Rename(temp, Path(gameID))
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
