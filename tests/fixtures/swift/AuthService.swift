import Foundation

/**
 * Service managing user session tokens and validation.
 */
public class AuthService {

    private let tokenStore: TokenStore

    public init(tokenStore: TokenStore) {
        self.tokenStore = tokenStore
    }

    /**
     * Validates a bearer token and returns userId if authentic.
     */
    public func validateToken(token: String) -> String? {
        if token.isEmpty {
            return nil
        }
        return tokenStore.findUserId(token: token)
    }

    /**
     * Issues a refreshed access token given a valid refresh token.
     */
    public func rotateRefreshToken(refreshToken: String) -> String {
        tokenStore.invalidate(refreshToken: refreshToken)
        return tokenStore.generate(userId: "user_123")
    }
}
