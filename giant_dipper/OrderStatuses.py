class OrderStatus:
    UNCONFIRMED = 'unconfirmed'
    CANCELLED = 'canceled'
    REJECTED = 'rejected'
    OPEN = 'confirmed'
    PARTIALLY_FILLED = 'partially_filled'
    FILLED = 'filled'


OPEN_ORDER_STATUSES = [OrderStatus.UNCONFIRMED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
REPLACE_ORDER_STATUSES = [OrderStatus.CANCELLED, OrderStatus.REJECTED]
