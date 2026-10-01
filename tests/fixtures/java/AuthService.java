package com.acme.auth;

import java.util.Optional;

/**
 * Service managing user session tokens and JWT validation.
 */
public class AuthService {

    private final TokenStore tokenStore;

    public AuthService(TokenStore tokenStore) {
        this.tokenStore = tokenStore;
    }

    /**
     * Validates a bearer token and returns userId if authentic.
     */
    public Optional<String> validateToken(String token) {
        if (token == null || token.isBlank()) {
            return Optional.empty();
        }
        return tokenStore.findUserId(token);
    }

    /**
     * Issues a refreshed access token given a valid refresh token.
     */
    public String rotateRefreshToken(String refreshToken) {
        tokenStore.invalidate(refreshToken);
        return tokenStore.generate("user_123");
    }
}
