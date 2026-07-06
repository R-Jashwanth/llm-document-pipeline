from typing import Dict

# --- Custom Exceptions ---
class InventoryShortageError(Exception):
    """Raised when there is not enough item stock."""
    pass

class PaymentFailedError(Exception):
    """Raised when the payment gateway rejects the transaction."""
    pass

class InvalidOrderError(Exception):
    """Raised when the order violates business rules."""
    pass

# --- External Service Interfaces (To be Mocked) ---
class InventoryService:
    def get_stock(self, product_id: str) -> int:
        """Connects to DB to check stock."""
        raise NotImplementedError("Real connection required")

    def decrement_stock(self, product_id: str, quantity: int):
        """Connects to DB to reduce stock."""
        raise NotImplementedError("Real connection required")

class PaymentGateway:
    def charge(self, amount: float, currency: str) -> bool:
        """Connects to Stripe/PayPal."""
        raise NotImplementedError("Real connection required")

# --- Main Business Logic ---
class Order:
    def __init__(self, 
                 inventory_service: InventoryService, 
                 payment_gateway: PaymentGateway,
                 customer_email: str,
                 is_vip: bool = False):
        
        self.inventory = inventory_service
        self.payment = payment_gateway
        self.customer_email = customer_email
        self.is_vip = is_vip
        self.items: Dict[str, Dict] = {} # {product_id: {'price': float, 'qty': int}}
        self.is_paid = False
        self.status = "DRAFT"

    def add_item(self, product_id: str, price: float, quantity: int = 1):
        """Adds items to the cart. Rejects invalid prices or quantities."""
        if price < 0:
            raise ValueError("Price cannot be negative")
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        if product_id in self.items:
            self.items[product_id]['qty'] += quantity
        else:
            self.items[product_id] = {'price': price, 'qty': quantity}

    def remove_item(self, product_id: str):
        """Removes an item entirely from the cart."""
        if product_id in self.items:
            del self.items[product_id]

    @property
    def total_price(self) -> float:
        """Calculates raw total before discounts."""
        return sum(item['price'] * item['qty'] for item in self.items.values())

    def apply_discount(self) -> float:
        """
        Applies business logic:
        1. VIPs get flat 20% off.
        2. Regulars get 10% off if total > 100.
        3. No discount otherwise.
        """
        total = self.total_price
        
        if self.is_vip:
            return round(total * 0.8, 2)
        elif total > 100:
            return round(total * 0.9, 2)
        
        return round(total, 2)

    def checkout(self):
        """
        Orchestrates the checkout process:
        1. Validates cart is not empty.
        2. Checks stock for all items.
        3. Calculates final price.
        4. Charges payment.
        5. Updates inventory.
        """
        if not self.items:
            raise InvalidOrderError("Cannot checkout an empty cart")

        # 1. Check Inventory Logic
        for product_id, data in self.items.items():
            available_stock = self.inventory.get_stock(product_id)
            if available_stock < data['qty']:
                raise InventoryShortageError(f"Not enough stock for {product_id}")

        # 2. Calculate Final Price
        final_amount = self.apply_discount()

        # 3. Process Payment
        try:
            success = self.payment.charge(final_amount, "USD")
            if not success:
                raise PaymentFailedError("Transaction declined by gateway")
        except Exception as e:
            # Catching generic network errors from the gateway
            raise PaymentFailedError(f"Payment gateway error: {str(e)}")

        # 4. Decrement Stock (Only occurs if payment succeeded)
        for product_id, data in self.items.items():
            self.inventory.decrement_stock(product_id, data['qty'])

        self.is_paid = True
        self.status = "COMPLETED"
        
        return {"status": "success", "charged_amount": final_amount}