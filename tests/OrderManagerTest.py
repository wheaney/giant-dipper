import math
from unittest import TestCase

from OrderManager import OrderManager
from OrderSides import OrderSide
from OrderStatuses import OrderStatus
from StateManagers import InMemoryStateManager


class FakeOrderService:
    def __init__(self, holdings, buying_power):
        self.holdings = holdings
        self.buying_power = buying_power

    def get_holdings(self):
        return self.holdings

    def get_buying_power(self):
        return self.buying_power

    def get_quote(self):
        return 1


def order_manager(holdings=10000, buying_power=10000, order_holding_threshold=0.25, terminal_sell_quantity=None,
                  terminal_buy_quantity=None, window_duration=5):
    om = OrderManager(
        order_service=FakeOrderService(holdings, buying_power),
        state_manager=InMemoryStateManager(terminal_sell_quantity, terminal_buy_quantity),
        price_increment_ratio=1.1,
        order_quantity_ratio=0.1,
        order_holdings_threshold=order_holding_threshold,
        window_duration=window_duration,
        window_factor=0.9,
        silent=True
    )
    om.cache_service_values()

    return om


def set_order_attributes(om, side, window_size=None, window_duration_remaining=None, force_replace=False,
                         rh_order_status=None):
    orders = om.state_manager.open_orders
    if not orders:
        orders = {OrderSide.BUY: {}, OrderSide.SELL: {}}
        om.state_manager.open_orders = orders

    order = orders.get(side, {})
    orders[side] = order

    if window_size:
        order['window_size'] = window_size
    if window_duration_remaining:
        order['window_duration_remaining'] = window_duration_remaining
    if force_replace:
        order['force_replace'] = force_replace
    if rh_order_status:
        om.rh_orders = om.rh_orders or {OrderSide.BUY: {}, OrderSide.SELL: {}}
        om.rh_orders[side]['state'] = rh_order_status

    return om


class OrderManagerTest(TestCase):

    def __assert_order_details__(self, side, expected_price, expected_quantity, expected_price_ratio,
                                 expected_window_size, base_price, window_size, window_duration=5):
        next_base_price, next_price, next_quantity, next_price_ratio, next_window_size = \
            order_manager(window_duration=window_duration).get_next_order_details(side, base_price, window_size)

        self.assertAlmostEqual(expected_price, next_price, 2)
        self.assertAlmostEqual(expected_quantity, next_quantity)
        self.assertAlmostEqual(expected_price_ratio, next_price_ratio)
        self.assertEqual(expected_window_size, next_window_size)

    def test_multiplier_for_window(self):
        self.assertEqual(1, order_manager().multiplier_for_window(0))
        self.assertEqual(1.9, order_manager().multiplier_for_window(1))
        self.assertEqual(2.8, order_manager().multiplier_for_window(2))

    def __assert_applied_multiplier__(self, expected_total_ratio, expected_complementary_ratio, ratio, multiplier):
        actual_total, actual_complementary = order_manager().apply_multiplier_to_ratio(ratio, multiplier)
        self.assertAlmostEqual(expected_total_ratio, actual_total)
        self.assertAlmostEqual(expected_complementary_ratio, actual_complementary)

    def test_apply_multiplier_to_ratio(self):
        self.__assert_applied_multiplier__(0.25, 0.75, 0.25, 1)
        self.__assert_applied_multiplier__(0.35048095, 0.64951905, 0.25, 1.5)
        self.__assert_applied_multiplier__(0.4375, 0.5625, 0.25, 2)

    def test_total_holdings(self):
        self.assertEqual(20000, order_manager().total_holdings(1))
        self.assertEqual(30000, order_manager().total_holdings(0.5))
        self.assertEqual(110000, order_manager().total_holdings(0.1))

    def test_account_value(self):
        self.assertEqual(20000, order_manager().account_value(1))
        self.assertEqual(15000, order_manager().account_value(0.5))
        self.assertEqual(11000, order_manager().account_value(0.1))

    def test_next_buy_quantity(self):
        # total_holdings (current_holdings plus converted buying_power) at $1 is 20k
        # mult of 4, ~34% (6.8k) doesn't exceed holdings threshold of ~68% (6.8k), use former
        self.assertAlmostEqual(6835, order_manager().next_quantity(OrderSide.BUY, 1.25, 1, 4))

        # mult of 5, ~41% (8.2k) DOES exceed holdings threshold of 76% (7626), use latter
        self.assertAlmostEqual(7626, order_manager().next_quantity(OrderSide.BUY, 1.25, 1, 5))

        # sell side is limited by low current holdings, don't exceed max sell quantity
        self.assertAlmostEqual(1249, order_manager(holdings=3000).next_quantity(OrderSide.BUY, 1.25, 1, 1))

        # order_holding_threshold at 100%, ignore opposite side for determining next quantity
        self.assertAlmostEqual(1300, order_manager(holdings=3000,
                                                   order_holding_threshold=1).next_quantity(OrderSide.BUY, 1.25, 1, 1))

        # 90% of holdings rounds to quantity of 4, leaves us the minimum buying power, unset terminal value
        om = order_manager(buying_power=20, order_holding_threshold=0.9)
        self.assertAlmostEqual(18, om.next_quantity(OrderSide.BUY, 1.25, 1, 1))
        self.assertIsNone(om.state_manager.terminal_quantity[OrderSide.BUY])

        # 99.9% of holdings rounds to quantity of 499, doesn't leave us minimum buying power, set terminal value same
        # as next quantity since window size was 1
        om = order_manager(buying_power=500, order_holding_threshold=0.999)
        self.assertAlmostEqual(499, om.next_quantity(OrderSide.BUY, 1.25, 1, 1))
        self.assertEqual(499, om.state_manager.terminal_quantity[OrderSide.BUY])

        # 99.9% of holdings rounds to quantity of 499, doesn't leave us minimum buying power, set terminal value as if
        # the last step had been a window size of 1: 99% of holdings for window size 2 vs 99.9% for window size 3 is
        # 499 minus 495 for a terminal quantity of 4)
        om = order_manager(buying_power=500, order_holding_threshold=0.9)
        self.assertAlmostEqual(499, om.next_quantity(OrderSide.BUY, 1.25, 1, 3))
        self.assertEqual(4, om.state_manager.terminal_quantity[OrderSide.BUY])

        # 100% of holdings with window size greater than 1 should leave us with the minimum terminal quantity since
        # computing the window size 1 quantity leaves us below the minimum
        om = order_manager(buying_power=100, order_holding_threshold=1)
        self.assertAlmostEqual(100, om.next_quantity(OrderSide.BUY, 1.25, 1, 2))
        self.assertEqual(1, om.state_manager.terminal_quantity[OrderSide.BUY])

        # if sell side has zero quantity, use terminal value, if available
        self.assertAlmostEqual(100, order_manager(holdings=0,
                                                  terminal_sell_quantity=100).next_quantity(OrderSide.BUY, 1.25, 1, 1))
        self.assertAlmostEqual(100, order_manager(holdings=1,
                                                  terminal_sell_quantity=100).next_quantity(OrderSide.BUY, 1.25, 1, 1))

        # if sell side has zero quantity and no terminal value is set, use minimum
        self.assertAlmostEqual(1, order_manager(holdings=0).next_quantity(OrderSide.BUY, 1.25, 1, 1))

    def test_next_sell_quantity(self):
        # total_holdings (current_holdings plus converted buying_power) at $1 is 20k
        # mult of 4, ~34% (6.8k) doesn't exceed holdings threshold of ~68% (6.8k), use former
        self.assertAlmostEqual(6835, order_manager().next_quantity(OrderSide.SELL, 0.8, 1, 4))

        # mult of 5, ~41% (8.2k) DOES exceed holdings threshold of 76% (7626), use latter
        self.assertAlmostEqual(7626, order_manager().next_quantity(OrderSide.SELL, 0.8, 1, 5))

        # buy side is limited by low buying power, don't exceed max buy quantity
        self.assertAlmostEqual(1249, order_manager(buying_power=3000).next_quantity(OrderSide.SELL, 0.8, 1, 1))

        # order_holding_threshold at 100%, ignore opposite side for determining next quantity
        self.assertAlmostEqual(1300, order_manager(buying_power=3000,
                                                   order_holding_threshold=1).next_quantity(OrderSide.SELL, 0.8, 1, 1))

        # 90% of holdings rounds to quantity of 4, leaves us the minimum buying power, unset terminal value
        om = order_manager(holdings=20, order_holding_threshold=0.9)
        self.assertAlmostEqual(18, om.next_quantity(OrderSide.SELL, 0.8, 1, 1))
        self.assertIsNone(om.state_manager.terminal_quantity[OrderSide.SELL])

        # 90% of holdings rounds to quantity of 4, doesn't leave us minimum buying power, set terminal value
        om = order_manager(holdings=4, order_holding_threshold=0.9)
        self.assertAlmostEqual(3, om.next_quantity(OrderSide.SELL, 0.8, 1, 1))
        self.assertEqual(3, om.state_manager.terminal_quantity[OrderSide.SELL])

        # if buy side has minimum buying_power, use terminal value, if available
        self.assertAlmostEqual(100, order_manager(buying_power=0,
                                                  terminal_buy_quantity=100).next_quantity(OrderSide.SELL, 0.8, 1, 1))
        self.assertAlmostEqual(100, order_manager(buying_power=1,
                                                  terminal_buy_quantity=100).next_quantity(OrderSide.SELL, 0.8, 1, 1))

        # if buy side has zero buying_power and no terminal value is set, use minimum
        self.assertAlmostEqual(1, order_manager(buying_power=0).next_quantity(OrderSide.SELL, 0.8, 1, 1))

    def test_should_replace_order(self):
        self.assertFalse(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                window_size=1,
                window_duration_remaining=5,
                rh_order_status=OrderStatus.OPEN
            ).should_replace_order(OrderSide.BUY)
        )

        # true if force_replace is set
        self.assertTrue(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                force_replace=True,
                window_size=1,
                window_duration_remaining=5,
                rh_order_status=OrderStatus.OPEN
            ).should_replace_order(OrderSide.BUY)
        )

        # true if next window size (based on duration remaining) is 1 less than the current window_size
        self.assertTrue(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=5,
                rh_order_status=OrderStatus.OPEN
            ).should_replace_order(OrderSide.BUY)
        )

        # false for previous test case setup if window_duration isn't set, as window_size isn't even considered
        self.assertFalse(
            set_order_attributes(
                order_manager(window_duration=None),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=5,
                rh_order_status=OrderStatus.OPEN
            ).should_replace_order(OrderSide.BUY)
        )

        # true if the rh_order status is in the replacement statuses list
        self.assertTrue(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                window_size=1,
                window_duration_remaining=5,
                rh_order_status=OrderStatus.CANCELLED
            ).should_replace_order(OrderSide.BUY)
        )

    def test_decrement_window(self):
        # decrement window_duration_remaining, still greater than window_duration, don't replace
        self.assertFalse(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=7,
                rh_order_status=OrderStatus.OPEN
            ).decrement_window(OrderSide.BUY)
        )

        # decrement window_duration_remaining, now equals window_duration, replace
        self.assertTrue(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=6,
                rh_order_status=OrderStatus.OPEN
            ).decrement_window(OrderSide.BUY)
        )

        # ignore window-specific cases if window_duration is not set
        self.assertFalse(
            set_order_attributes(
                order_manager(window_duration=None),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=6,
                rh_order_status=OrderStatus.OPEN
            ).decrement_window(OrderSide.BUY)
        )

        # return True if should_replace_order is True (e.g. order is cancelled), even if window-specific cases
        # won't trigger a replacement
        self.assertTrue(
            set_order_attributes(
                order_manager(),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=7,
                rh_order_status=OrderStatus.CANCELLED
            ).decrement_window(OrderSide.BUY)
        )

        self.assertTrue(
            set_order_attributes(
                order_manager(window_duration=None),
                OrderSide.BUY,
                window_size=2,
                window_duration_remaining=6,
                rh_order_status=OrderStatus.CANCELLED
            ).decrement_window(OrderSide.BUY)
        )

    def test_sell_price_too_low(self):
        # price is too low if we go one window_factor up and it's still below the current price.
        # with sell ratio of 1.1 and window factor of 0.9, next step is about 20% higher than the price
        # 120% of $0.85 is $1.02, higher than current price, return false
        self.assertFalse(order_manager().sell_price_too_low(0.85))

        # 120% of $0.8 is $0.96, lower than current price, return true
        self.assertTrue(order_manager().sell_price_too_low(0.8))

    def test_buy_price_too_high(self):
        # current_price is $1
        # price is too high if we go one window_factor down and it's still above the current price.
        # with buy ratio of 0.909 and window factor of 0.9, next step is about 16.6% lower than the price
        # 83.4% of $1.15 is $0.96, lower than current price, return false
        self.assertFalse(order_manager().buy_price_too_high(1.15))

        # 83.4% of $1.20 is $1.001, higher than current price, return true
        self.assertTrue(order_manager().buy_price_too_high(1.2))

    def test_get_next_order_details(self):
        # current_price is $1

        # sell price is not too low with a window_size of 0, expect to return with same window size
        self.__assert_order_details__(OrderSide.SELL,
                                      expected_price=1,
                                      expected_quantity=2000,
                                      expected_price_ratio=1.1,
                                      expected_window_size=0,
                                      base_price=1 / 1.1,
                                      window_size=0)

        # sell price is too low with a window_size of 0, expect to increment the window size and return new values
        # we know from our sell_price_too_low test that a price of $0.80 will trigger this case, so we'll reverse
        # engineer the base_price from this value
        first_attempt_sell_price = 0.8
        base_price = first_attempt_sell_price / 1.1

        expected_multiplier = 1.9
        expected_price_ratio = pow(1.1, expected_multiplier)
        expected_price = base_price * expected_price_ratio
        expected_applied_ratio = 0.181420681525
        expected_quantity = math.floor(((10000 / expected_price) + 10000) * expected_applied_ratio)
        self.__assert_order_details__(OrderSide.SELL,
                                      expected_price=expected_price,
                                      expected_quantity=expected_quantity,
                                      expected_price_ratio=expected_price_ratio,
                                      expected_window_size=1,
                                      base_price=base_price,
                                      window_size=0)

        # same as previous test case, but window_duration is not set, window size is always expected to be 0
        # even if a multiplier is applied
        self.__assert_order_details__(OrderSide.SELL,
                                      expected_price=expected_price,
                                      expected_quantity=expected_quantity,
                                      expected_price_ratio=expected_price_ratio,
                                      expected_window_size=0,
                                      base_price=base_price,
                                      window_size=0,
                                      window_duration=None)
