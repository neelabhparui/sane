"""Payment processing and token capture service."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentToken:
    token_id: str
    amount: float
    currency: str = "USD"


class PaymentGateway:
    """Gateway interface for credit card processors."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def process_charge(self, token: PaymentToken) -> bool:
        """Charges the customer token with upstream merchant."""
        return True


class PaymentRetryCoordinator:
    """Handles transient payment failures and scheduled retries."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts

    def should_retry(self, attempt: int, error_code: str) -> bool:
        """Determines if a failure is retriable based on bank response code."""
        if attempt >= self.max_attempts:
            return False
        return error_code in ("TIMEOUT", "NETWORK_ERROR")

    async def schedule_retry(self, token_id: str, delay_seconds: int = 60) -> None:
        """Schedules exponential backoff retry task in queue."""
        pass


class PaymentService:
    """Core payment business logic service."""

    def __init__(self, gateway: PaymentGateway, retry_coord: PaymentRetryCoordinator):
        self.gateway = gateway
        self.retry_coord = retry_coord

    def capture(self, token: PaymentToken) -> bool:
        """Captures payment for an order and records transaction."""
        success = self.gateway.process_charge(token)
        if not success:
            self.retry_coord.should_retry(1, "TIMEOUT")
        return success
