import math
import sys

from giant_dipper.OrderSides import OrderSide
from giant_dipper.OrderStatuses import OrderStatus, OPEN_ORDER_STATUSES, REPLACE_ORDER_STATUSES

BUY_ORDER_COLLAR = 1.0025
SELL_ORDER_COLLAR = 1 / BUY_ORDER_COLLAR


def opposite_side(side):
    return OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY


PRICE_FLOOR_MULTIPLIER = pow(10, 5)  # we'll floor prices to 5 digits for ordering


# floors the price to 5 digits, don't want to round as that may result in rounding up beyond the bounds of our current
# holdings/buying power
def price_floor(price):
    return math.floor(price * PRICE_FLOOR_MULTIPLIER) / PRICE_FLOOR_MULTIPLIER


class OrderManager:
    def __init__(self, order_service, state_manager, price_increment_ratio, order_quantity_ratio,
                 order_holdings_threshold, window_duration=None, window_factor=1, silent=False,
                 rebalance_interval=None, round_quantity_digits=0, rebalance_threshold=None):
        self.rh_orders = {}
        self.current_price = None
        self.current_holdings = None
        self.current_buying_power = None
        self.order_service = order_service
        self.state_manager = state_manager
        self.sell_ratio = price_increment_ratio
        self.buy_ratio = 1 / price_increment_ratio
        self.order_holdings_threshold = order_holdings_threshold
        self.window_duration = window_duration
        self.order_quantity_ratio = order_quantity_ratio
        self.silent = silent
        self.rebalance_interval = rebalance_interval
        self.window_factor = window_factor
        self.round_quantity_digits = round_quantity_digits
        self.minimum_quantity = pow(10, -self.round_quantity_digits)
        self.rebalance_threshold = rebalance_threshold

    # retrieve and cache all values from the service that are needed for a single run
    def cache_service_values(self):
        self.current_price = self.order_service.get_quote()
        self.current_holdings = self.order_service.get_holdings()
        self.current_buying_power = self.order_service.get_buying_power()
        if self.state_manager.open_orders:
            self.rh_orders = {
                OrderSide.SELL: self.order_service.get_order_info(
                    self.state_manager.open_orders[OrderSide.SELL][
                        'id']) if OrderSide.SELL in self.state_manager.open_orders else None,
                OrderSide.BUY: self.order_service.get_order_info(
                    self.state_manager.open_orders[OrderSide.BUY][
                        'id']) if OrderSide.BUY in self.state_manager.open_orders else None
            }

    # primary method to be invoked at each interval
    def run(self):
        self.cache_service_values()

        self.state_manager.record_base_metrics(self.current_price, self.current_holdings, self.current_buying_power)
        self.check_orders()
        self.check_rebalance()

    # current buy price quote including collar
    def current_buy_price(self):
        return self.current_price * BUY_ORDER_COLLAR

    # current sell price quote including collar
    def current_sell_price(self):
        return self.current_price * SELL_ORDER_COLLAR

    # determine the appropriate quantity/price multiplier given window size
    def multiplier_for_window(self, window_size):
        return (window_size * self.window_factor) + 1

    # compute the ratio and complementary ratio when applying a given multiplier
    def apply_multiplier_to_ratio(self, ratio, multiplier):
        complementary_ratio = pow(1 - ratio, multiplier)

        # floating point math is imprecise, round to expected decimal value if repeating 9s
        total_ratio = round(1 - complementary_ratio, 10)

        return total_ratio, complementary_ratio

    # return the next quantity given the price and multiplier, taking into account the order holdings threshold
    # and whether the opposite side has recently run against limits
    def next_quantity(self, side, base_price, for_price, multiplier):  # noqa: C901
        if side == OrderSide.BUY and self.current_buying_power / for_price <= self.minimum_quantity:
            return 0

        multiplied_order_ratio = self.apply_multiplier_to_ratio(self.order_quantity_ratio, multiplier)[0]
        default_quantity = self.total_holdings(for_price) * multiplied_order_ratio
        total_threshold, complementary_total_threshold = self.apply_multiplier_to_ratio(self.order_holdings_threshold,
                                                                                        multiplier)

        # determine the max quantity when applying the order_holdings_threshold to this order side
        if side == OrderSide.SELL:
            this_max_quantity = self.current_holdings * total_threshold
        else:
            this_max_quantity = (self.current_buying_power * total_threshold) / for_price

        if opposite_side(side) == OrderSide.SELL:
            opposite_side_quantity_available = self.current_holdings * base_price / for_price
        else:
            opposite_side_quantity_available = self.current_buying_power / base_price

        terminal_quantities = self.state_manager.terminal_quantity

        if self.quantity_floor(opposite_side_quantity_available) <= self.minimum_quantity:
            opposite_max_quantity = terminal_quantities[opposite_side(side)] or self.minimum_quantity
        elif complementary_total_threshold > 0:
            # determine the max quantity when applying the order_holdings_threshold to the opposite order side, this
            # makes sure we're limiting the size of this side's orders if the other side was limited on previous orders
            inverse_total_threshold = (1 / complementary_total_threshold) - 1
            opposite_max_quantity = opposite_side_quantity_available * inverse_total_threshold
        else:
            # entirety of holdings can be bought/sold and previous terminal value wasn't set, set opposite_max_holdings
            # to max to disqualify it from winning the min() call below
            opposite_max_quantity = sys.maxsize

        next_quantity = self.quantity_floor(min(default_quantity, this_max_quantity, opposite_max_quantity))

        # if the proposed quantity would result in an exhaustion of holdings/buying_power, record it so it can be
        # reversed if it's filled
        if next_quantity > 0:
            adjusted_terminal_quantity = next_quantity
            if multiplier > 1:
                # window was greater than 1, adjust the terminal quantity so it represents a window size of 1
                stepped_down_multiplier = multiplier - 1
                stepped_down_total_threshold = self.apply_multiplier_to_ratio(
                    self.order_holdings_threshold,
                    stepped_down_multiplier
                )[0]

                # find the percentage difference between a window size of 1 and the current window size
                stepped_down_threshold_delta = 1 - (stepped_down_total_threshold / total_threshold)
                adjusted_terminal_quantity = self.quantity_floor(stepped_down_threshold_delta * next_quantity)
                adjusted_terminal_quantity = max(adjusted_terminal_quantity, self.minimum_quantity)

            if side == OrderSide.SELL:
                if self.quantity_floor(self.current_holdings - next_quantity) <= self.minimum_quantity:
                    terminal_quantities[side] = adjusted_terminal_quantity
                else:
                    terminal_quantities[side] = None
            else:
                if self.quantity_floor(
                        (self.current_buying_power / for_price) - next_quantity) <= self.minimum_quantity:
                    terminal_quantities[side] = adjusted_terminal_quantity
                else:
                    terminal_quantities[side] = None

        return next_quantity

    # floors the quantity to the appropriate number of digits, don't want to round as that may result in rounding up
    # beyond the bounds of our current holdings/buying power
    def quantity_floor(self, quantity):
        digits_multiplier = pow(10, self.round_quantity_digits)
        return math.floor(quantity * digits_multiplier) / digits_multiplier

    # check whether any orders are filled or need to be replaced with a narrower window size
    def check_orders(self):
        if self.state_manager.open_orders:
            rh_sell_order = self.rh_orders[OrderSide.SELL]
            rh_buy_order = self.rh_orders[OrderSide.BUY]
            if rh_sell_order and rh_sell_order['state'] == OrderStatus.FILLED:
                filled_side = OrderSide.SELL
                self.order_filled(rh_sell_order)
                if rh_buy_order and rh_buy_order['state'] == OrderStatus.FILLED:
                    self.order_filled(rh_buy_order)
                    if rh_buy_order['last_transaction_at'] > rh_sell_order['last_transaction_at']:
                        filled_side = OrderSide.BUY

                self.replace_orders(filled_side)
            elif rh_buy_order and rh_buy_order['state'] == OrderStatus.FILLED:
                self.order_filled(rh_buy_order)
                self.replace_orders(OrderSide.BUY)
            else:
                if not self.silent:
                    print("\tNo orders filled")

                for side in [OrderSide.BUY, OrderSide.SELL]:
                    if self.decrement_window(side):
                        open_order = self.state_manager.open_orders[side]

                        base_price, price, quantity, price_ratio, next_window_size = \
                            self.get_next_order_details(
                                side=side,
                                base_price=open_order['base_price'],
                                window_size=self.window_size(open_order['window_duration_remaining'])
                            )
                        self.place_order(side, base_price, price, quantity, next_window_size)
        else:
            self.state_manager.open_orders = {}
            self.create_new_orders()

    def window_size(self, duration_remaining):
        return math.ceil(duration_remaining / self.window_duration) if self.window_duration else 0

    # checks whether rebalancing is needed, and executes if necessary
    def check_rebalance(self):  # noqa: C901
        if self.rebalance_interval:
            rebalance_to_price = self.state_manager.record_check_rebalance(self.current_price, self.rebalance_interval,
                                                                           self.rebalance_threshold)
            if rebalance_to_price:
                if not self.silent:
                    print("\tRebalance; holdings: {}, buying_power: ${}, to_price: ${}".format(
                        self.current_holdings, self.current_buying_power, rebalance_to_price
                    ))

                # rebalance to half holdings and half cash
                target_holdings = self.total_holdings(rebalance_to_price) / 2
                target_cash_value = self.account_value(rebalance_to_price) / 2

                # cancel open orders before attempting to place new ones, otherwise they'll probably get rejected
                for side in [OrderSide.BUY, OrderSide.SELL]:
                    if side in self.rh_orders and self.rh_orders[side] and \
                            self.rh_orders[side]['state'] in OPEN_ORDER_STATUSES:
                        if not self.silent:
                            print("\tCanceling {} order: {}".format(side, self.rh_orders[side]))
                        self.order_service.cancel_order(self.rh_orders[side]['id'])

                rh_order = None
                if self.current_buying_power > target_cash_value:
                    buy_value = self.current_buying_power - target_cash_value
                    if not self.silent:
                        print("\tRebalance: purchasing ${}".format(buy_value))

                    rh_order = self.order_service.order_buy(buy_value)
                elif target_holdings < self.current_holdings:
                    sell_quantity = self.current_holdings - target_holdings
                    if not self.silent:
                        print("\tRebalance: selling {}".format(sell_quantity))

                    rh_order = self.order_service.order_sell(self.quantity_floor(sell_quantity))

                if rh_order:
                    if 'id' in rh_order and rh_order['state'] == OrderStatus.FILLED:
                        self.state_manager.record_order(rh_order, for_rebalance=True)

                        # re-cache values from the service, as they've changed after rebalancing
                        self.cache_service_values()
                        self.create_new_orders()
                    else:
                        if not self.silent:
                            print("\tError placing {} order: {}".format(rh_order['side'], rh_order))

    # decrements the window size, returns true if order should be canceled and re-created with a narrower price window
    def decrement_window(self, side):
        if side not in self.state_manager.open_orders:
            return False

        if self.window_duration:
            open_order = self.state_manager.open_orders[side]
            window_duration_remaining = open_order['window_duration_remaining']
            open_order['window_duration_remaining'] = \
                window_duration_remaining - 1 if window_duration_remaining > 0 else 0

        return self.should_replace_order(side)

    def should_replace_order(self, side):
        order = self.state_manager.open_orders[side]
        if order.get('force_replace') or self.rh_orders[side]['state'] in REPLACE_ORDER_STATUSES:
            return True

        if not self.window_duration:
            return False

        duration_remaining = order['window_duration_remaining']
        return order['window_size'] - self.window_size(duration_remaining) >= 1

    # builds next order details from a filled_request
    def get_next_order_details_for_filled(self, side, filled_request, filled_side):
        open_order = self.state_manager.open_orders[side] if side in self.state_manager.open_orders else None
        window_size = self.window_size(open_order['window_duration_remaining']) if open_order else 0
        if side == filled_side and self.window_duration:
            window_size += 1

        return self.get_next_order_details(
            side=side,
            window_size=window_size,
            base_price=filled_request['price']
        )

    # check if the proposed sell price is too low; use a window size of 1 for our check so the resulting limit price
    # can be allowed to remain one step under the current price, triggering an immediate sell at the optimum price
    # in the case of a large jump in price since the last order was filled
    def sell_price_too_low(self, price):
        if (price * pow(self.sell_ratio, self.multiplier_for_window(1))) < self.current_price:
            if not self.silent:
                print("\tNext sell price was too low (${} vs ${})".format(price, self.current_price))
            return True

        return False

    # check if the proposed buy price is too high; use a window size of 1 for our check so the resulting limit price
    # can be allowed to remain one step above the current price, triggering an immediate buy at the optimum price
    # in the case of a large jump in price since the last order was filled
    def buy_price_too_high(self, price):
        if (price * pow(self.buy_ratio, self.multiplier_for_window(1))) > self.current_price:
            if not self.silent:
                print("\tNext buy price was too high (${} vs ${})".format(price, self.current_price))
            return True

        return False

    # builds next orders details for a side given a base price (the last order price) and window size
    def get_next_order_details(self, side, base_price, window_size):
        price_ratio = self.sell_ratio if side == OrderSide.SELL else self.buy_ratio
        price_needs_fix = self.sell_price_too_low if side == OrderSide.SELL else self.buy_price_too_high
        next_window_size = window_size

        # grow the window size as needed to accommodate large price movements
        while True:
            multiplier = self.multiplier_for_window(next_window_size)
            next_price_ratio = pow(price_ratio, multiplier)
            next_price = base_price * next_price_ratio
            next_quantity = self.next_quantity(side, base_price, next_price, multiplier)

            if price_needs_fix(next_price):
                # price window is too narrow, increment window size
                next_window_size += 1
            else:
                break

        return base_price, next_price, next_quantity, next_price_ratio, next_window_size if self.window_duration else 0

    # process a filled order,
    def order_filled(self, rh_order):
        if not self.silent:
            print("\tOrder ({}) filled: {}".format(rh_order['side'], rh_order['id']))

        self.state_manager.record_order(rh_order)

    # attempt to place new buy and sell orders (place_order function may choose not to act)
    def replace_orders(self, filled_side):
        filled_request = self.state_manager.open_orders[filled_side]

        for side in [OrderSide.BUY, OrderSide.SELL]:
            base_price, price, quantity, price_ratio, window_size = \
                self.get_next_order_details_for_filled(side, filled_request, filled_side)
            self.place_order(side, base_price, price, quantity, window_size)

    # create new orders from a freshly computed base price
    def create_new_orders(self, base_price=None):
        base_sell_price, sell_price, sell_quantity, sell_ratio, next_sell_window_size = \
            self.get_next_order_details(
                side=OrderSide.SELL,
                base_price=base_price if base_price else self.current_price,
                window_size=0
            )

        base_buy_price, buy_price, buy_quantity, buy_ratio, next_buy_window_size = \
            self.get_next_order_details(
                side=OrderSide.BUY,
                base_price=base_price if base_price else self.current_price,
                window_size=0
            )

        if not self.silent:
            print("\tFound buy price {} and sell price {}".format(buy_price, sell_price))
        self.place_order(OrderSide.SELL, base_sell_price, sell_price, sell_quantity, next_sell_window_size)
        self.place_order(OrderSide.BUY, base_buy_price, buy_price, buy_quantity, next_buy_window_size)

    # create a new order given order details
    def place_order(self, side, base_price, price, quantity, window_size):
        if side in self.state_manager.open_orders:
            open_order = self.state_manager.open_orders[side]
            if quantity == 0:
                del self.state_manager.open_orders[side]
                return

            if base_price == open_order['base_price'] and not self.should_replace_order(side):
                return

            if self.rh_orders[side]['state'] in OPEN_ORDER_STATUSES:
                # cancel the order, record the new base price, and return without placing a new order,
                # on the next run it will be replaced assuming the status has changed by then
                if not self.silent:
                    print("\tCanceling {} order: {}".format(side, self.rh_orders[side]))
                self.order_service.cancel_order(open_order['id'])
                open_order['base_price'] = base_price
                return

        # don't round price in our internal dict, we'll round when calling the order function
        order = {
            'base_price': base_price,
            'price': price,
            'quantity': quantity,
            'window_size': window_size,
            'window_duration_remaining': window_size * self.window_duration if self.window_duration else 0
        }
        order_function = self.order_service.order_sell_limit if side == OrderSide.SELL \
            else self.order_service.order_buy_limit
        rh_order = order_function(order['quantity'], price_floor(order['price']))
        if 'id' in rh_order:
            order['id'] = rh_order['id']
            self.state_manager.open_orders[side] = order
            self.rh_orders[side] = rh_order
            if not self.silent:
                print("\tNew {} order: {}".format(side, order))
        else:
            if not self.silent:
                print("\tError placing {} order: {}".format(side, rh_order))

    # USD value of account, counts holdings and cash;
    # don't round, as this is an intermediate value when used in calculations
    def account_value(self, at_price):
        return (self.current_holdings * at_price) + self.current_buying_power

    # potential holdings of the account, current holdings plus cash if cash is converted to coin at the given price;
    # don't round, as this is an intermediate value when used in calculations
    def total_holdings(self, at_price):
        return self.current_holdings + (self.current_buying_power / at_price)
