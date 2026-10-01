# System Architecture

## Authentication

Authentication in the system is managed by the security module.

### Refresh tokens

Session persistence is maintained via JWT refresh tokens. When an access token expires, the client calls `AuthService.rotateRefreshToken` to obtain a fresh token pair. Invalid or revoked tokens result in immediate 401 unauthenticated response.

## Payments and Billing

All transactions are verified against the fraud detection service.

### Retry Policy

Payment retry behaviour is coordinated by `PaymentRetryCoordinator`. Transient network errors and gateway timeouts are automatically scheduled for retry with exponential backoff up to 3 attempts. Non-retriable errors like card decline immediately terminate the checkout flow.
