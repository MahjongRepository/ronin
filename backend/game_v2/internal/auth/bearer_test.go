package auth_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
)

func TestIsInternalBearer_WhenGivenAnAuthorizationHeader_ShouldMatchOnlyTheSecretAsBearer(t *testing.T) {
	for _, c := range []struct {
		name          string
		authorization string
		secret        string
		want          bool
	}{
		{"the secret as bearer", "Bearer internal-secret", "internal-secret", true},
		{"another token", "Bearer internal-secreT", "internal-secret", false},
		{"a token prefixing the secret", "Bearer internal", "internal-secret", false},
		{"no scheme", "internal-secret", "internal-secret", false},
		{"a lowercase scheme", "bearer internal-secret", "internal-secret", false},
		{"no header", "", "internal-secret", false},
		{"no secret configured", "Bearer ", "", false},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := auth.IsInternalBearer(c.authorization, c.secret); got != c.want {
				t.Errorf("IsInternalBearer(%q) = %v, want %v", c.authorization, got, c.want)
			}
		})
	}
}
