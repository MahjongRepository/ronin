package store_test

import (
	"bytes"
	"compress/gzip"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

func decompress(t *testing.T, compressed []byte) []byte {
	t.Helper()
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		t.Fatalf("gzip header: %v", err)
	}
	content, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("gunzip: %v", err)
	}
	return content
}

func assertMode(t *testing.T, path string, want fs.FileMode) {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != want {
		t.Errorf("%s mode = %v, %v; want %v", path, info, err, want)
	}
}

func TestReplaysSave_WhenGivenAReplay_ShouldStoreItGzippedInOwnerOnlyShards(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "replays")
	err := os.Mkdir(dir, 0o755)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	replays := store.NewReplays(dir)
	content := []byte("encoded replay records")

	err = replays.Save("abcd-game_1", content)
	if err != nil {
		t.Fatalf("Save: %v", err)
	}

	file := filepath.Join(dir, "ab", "cd", "abcd-game_1.msgpack.gz")
	stored, err := os.ReadFile(file)
	if err != nil {
		t.Fatalf("read stored replay: %v", err)
	}
	if got := decompress(t, stored); !bytes.Equal(got, content) {
		t.Errorf("stored replay = %q, want %q", got, content)
	}
	assertMode(t, file, 0o600)
	for _, d := range []string{dir, filepath.Join(dir, "ab"), filepath.Join(dir, "ab", "cd")} {
		assertMode(t, d, 0o700)
	}

	entries, err := os.ReadDir(filepath.Join(dir, "ab", "cd"))
	if err != nil || len(entries) != 1 {
		t.Errorf("shard entries = %v, %v; want only the replay", entries, err)
	}

	read, err := replays.Read("abcd-game_1")
	if err != nil || !bytes.Equal(read, stored) {
		t.Errorf("Read = %d bytes, %v; want the %d stored bytes", len(read), err, len(stored))
	}
}

func TestReplaysSave_WhenTheGameHasAReplay_ShouldReplaceIt(t *testing.T) {
	replays := store.NewReplays(t.TempDir())
	err := errors.Join(replays.Save("game-1", []byte("first")), replays.Save("game-1", []byte("second")))
	if err != nil {
		t.Fatalf("Save: %v", err)
	}

	read, err := replays.Read("game-1")
	if err != nil {
		t.Fatalf("Read: %v", err)
	}
	if got := decompress(t, read); string(got) != "second" {
		t.Errorf("stored replay = %q, want the second", got)
	}
}

func TestReplays_WhenTheGameIDCannotNameAReplay_ShouldRefuseIt(t *testing.T) {
	replays := store.NewReplays(t.TempDir())
	for _, id := range []string{"abc", strings.Repeat("a", 51), "ab/cd", "../../etc", "abcd\n", "abcd.e", "абвг"} {
		saveErr := replays.Save(id, []byte("x"))
		_, readErr := replays.Read(id)
		if !errors.Is(saveErr, store.ErrInvalidGameID) || !errors.Is(readErr, store.ErrInvalidGameID) {
			t.Errorf("%q: Save, Read errors = %v, %v; want %v", id, saveErr, readErr, store.ErrInvalidGameID)
		}
	}
}

func TestReplaysRead_WhenTheFileIsOverTheCap_ShouldRefuseIt(t *testing.T) {
	dir := t.TempDir()
	shard := filepath.Join(dir, "at", "ca")
	err := os.MkdirAll(shard, 0o700)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	for name, size := range map[string]int{"atcap": store.MaxReplayFileSize, "atcapplus1": store.MaxReplayFileSize + 1} {
		err = os.WriteFile(filepath.Join(shard, name+".msgpack.gz"), make([]byte, size), 0o600)
		if err != nil {
			t.Fatalf("write %s: %v", name, err)
		}
	}
	replays := store.NewReplays(dir)

	atCap, err := replays.Read("atcap")
	if err != nil || len(atCap) != store.MaxReplayFileSize {
		t.Errorf("Read at the cap = %d bytes, %v; want %d", len(atCap), err, store.MaxReplayFileSize)
	}

	_, err = replays.Read("atcapplus1")
	if !errors.Is(err, store.ErrReplayTooLarge) {
		t.Errorf("Read over the cap error = %v, want %v", err, store.ErrReplayTooLarge)
	}
}

func TestReplays_WhenALinkLeadsOutOfTheDirectory_ShouldNotFollowIt(t *testing.T) {
	dir, outside := t.TempDir(), t.TempDir()
	err := os.WriteFile(filepath.Join(outside, "game-1.msgpack.gz"), []byte("outside"), 0o600)
	if err != nil {
		t.Fatalf("write outside: %v", err)
	}
	err = os.Mkdir(filepath.Join(dir, "ga"), 0o700)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	err = os.Symlink(outside, filepath.Join(dir, "ga", "me"))
	if err != nil {
		t.Fatalf("symlink: %v", err)
	}
	replays := store.NewReplays(dir)

	_, readErr := replays.Read("game-1")
	saveErr := replays.Save("game-2", []byte("x"))
	if readErr == nil || saveErr == nil {
		t.Errorf("Read, Save errors = %v, %v; want both refused", readErr, saveErr)
	}

	entries, err := os.ReadDir(outside)
	if err != nil || len(entries) != 1 {
		t.Errorf("outside entries = %v, %v; want only its own file", entries, err)
	}
}

func TestReplaysRead_WhenNoReplayIsStored_ShouldAnswerNotExist(t *testing.T) {
	for _, dir := range []string{t.TempDir(), filepath.Join(t.TempDir(), "missing")} {
		_, err := store.NewReplays(dir).Read("abcd-1")
		if !errors.Is(err, fs.ErrNotExist) {
			t.Errorf("%s: Read error = %v, want %v", dir, err, fs.ErrNotExist)
		}
	}
}
