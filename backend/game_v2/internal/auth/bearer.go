package auth

import (
	"crypto/subtle"
	"strings"
)

const bearerPrefix = "Bearer "

// IsInternalBearer reports whether an Authorization header value carries secret as its bearer
// token, compared in constant time. An empty secret matches nothing.
func IsInternalBearer(authorization, secret string) bool {
	token, ok := strings.CutPrefix(authorization, bearerPrefix)
	if !ok || secret == "" {
		return false
	}

	return subtle.ConstantTimeCompare([]byte(token), []byte(secret)) == 1
}
