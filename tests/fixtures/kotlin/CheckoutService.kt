package com.acme.checkout

/**
 * High-level checkout coordinator processing user baskets.
 */
class CheckoutService(
    private val paymentProcessor: PaymentProcessor,
    private val inventoryManager: InventoryManager,
) {

    /**
     * Submits customer order, reserves inventory, and charges payment.
     */
    suspend fun submitOrder(orderId: String, token: String, total: Double): Boolean {
        inventoryManager.reserve(orderId)

        val result = paymentProcessor.capture(
            token,
            total,
        )

        return result
    }
}
