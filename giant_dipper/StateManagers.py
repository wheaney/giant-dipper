from os.path import exists

import yaml

from giant_dipper.OrderSides import OrderSide


def empty_metrics():
    return {'count': 0, 'order_value': 0.0, 'quantity': 0}


class BaseStateManager:

    # record baseline values for future comparison
    def record_base_metrics(self, coin_price, holdings, buying_power):
        if 'initial_price' not in self.metrics:
            self.metrics['initial_price'] = coin_price

        if 'initial_holdings' not in self.metrics:
            self.metrics['initial_holdings'] = holdings

        if 'initial_buying_power' not in self.metrics:
            self.metrics['initial_buying_power'] = buying_power

        if 'ticks_from_start' not in self.metrics:
            self.metrics['ticks_from_start'] = 0
        else:
            self.metrics['ticks_from_start'] += 1

        if 'longest_ticks_between_orders' not in self.metrics:
            self.metrics['longest_ticks_between_orders'] = 0

        if 'ticks_since_last_order_execution' not in self.metrics:
            self.metrics['ticks_since_last_order_execution'] = 0
        else:
            self.metrics['ticks_since_last_order_execution'] += 1

        if self.metrics['ticks_since_last_order_execution'] > self.metrics['longest_ticks_between_orders']:
            self.metrics['longest_ticks_between_orders'] = self.metrics['ticks_since_last_order_execution']

        self.metrics['last_price'] = coin_price

    def record_order(self, rh_order, for_rebalance=False):
        self._record_order_metrics(rh_order, for_rebalance)

        if 'rebalance' in self.metrics:
            del self.metrics['rebalance']

    # record metrics for an order
    def _record_order_metrics(self, rh_order, for_rebalance):
        if not for_rebalance:
            self.metrics['ticks_since_last_order_execution'] = 0

        if rh_order['side'] in self.metrics:
            side_metrics = self.metrics[rh_order['side']]
        else:
            side_metrics = empty_metrics()
            self.metrics[rh_order['side']] = side_metrics

        if not for_rebalance:
            side_metrics['count'] += 1
        side_metrics['order_value'] += float(rh_order['rounded_executed_notional'])
        side_metrics['quantity'] += round(float(rh_order['quantity']))

    # record the current price, return the average price if a rebalance should occur, otherwise None
    def record_check_rebalance(self, current_price, rebalance_interval, rebalance_threshold):
        if 'rebalance' not in self.metrics:
            usd_gained, coin_gained, last_price, current_holdings, current_buying_power, current_account_value = \
                self.account_values()
            buying_power_perc = current_buying_power / current_account_value
            holdings_perc = (current_holdings * current_price) / current_account_value
            if not rebalance_threshold or abs(buying_power_perc - holdings_perc) > rebalance_threshold:
                self.reset_rebalance_metrics()

        if 'rebalance' in self.metrics:
            rebalance = self.metrics['rebalance']
            rebalance['count'] += 1
            rebalance['total_price'] += current_price

            if rebalance['count'] >= rebalance_interval:
                return rebalance['total_price'] / rebalance['count']

    def reset_rebalance_metrics(self):
        self.metrics['rebalance'] = {
            'count': 0,
            'total_price': 0.0
        }

    def account_values(self):
        if self.metrics:
            buys = self.metrics.get(OrderSide.BUY, empty_metrics())
            sells = self.metrics.get(OrderSide.SELL, empty_metrics())
            usd_gained = sells['order_value'] - buys['order_value']
            coin_gained = buys['quantity'] - sells['quantity']
            last_price = self.metrics['last_price']
            current_holdings = self.metrics['initial_holdings'] + coin_gained
            current_buying_power = self.metrics['initial_buying_power'] + usd_gained
            current_account_value = current_holdings * last_price + current_buying_power

            return usd_gained, coin_gained, last_price, current_holdings, current_buying_power, current_account_value

        return 0, 0, 0, 0, 0, 0

    # computes and returns all metrics
    def compute_metrics(self):
        if self.metrics:
            usd_gained, coin_gained, last_price, current_holdings, current_buying_power, current_account_value = \
                self.account_values()
            initial_price = float(self.metrics['initial_price'])
            price_change_percent = last_price / initial_price
            initial_account_value = self.metrics['initial_holdings'] * initial_price + self.metrics[
                'initial_buying_power']
            account_value_change_percent = current_account_value / initial_account_value

            return round(usd_gained, 2), round(coin_gained), round(account_value_change_percent, 5), round(
                price_change_percent, 5)

        return 0, 0, 0, 0

    # prints collected metrics
    def print_metrics(self):
        if self.metrics and self.open_orders:
            usd_gained, coin_gained, account_value_change_percent, price_change_percent = self.compute_metrics()

            print("\tMetrics:")
            print("\t\tNet change in USD: ${}".format(usd_gained))
            print("\t\tNet change in coin: {}".format(coin_gained))
            print("\t\tAccount value change percent: {}%".format(round(account_value_change_percent * 100, 1)))
            print("\t\tCoin price change percent: {}%".format(round(price_change_percent * 100, 1)))


class FileStateManager(BaseStateManager):
    def __init__(self, orders_file_path, historical_orders_file_path):
        self.orders_file_path = orders_file_path
        self.historical_orders_file_path = historical_orders_file_path

        self.open_orders = None
        self.metrics = {}
        self.terminal_quantity = {OrderSide.BUY: None, OrderSide.SELL: None}
        if exists(orders_file_path):
            with open(orders_file_path, 'r') as orders_file:
                orders = yaml.safe_load(orders_file) or {}
                self.open_orders = orders.get('orders')
                self.metrics = orders.get('metrics', {})
                self.terminal_quantity = orders.get('terminal_quantity') or self.terminal_quantity

    def record_order(self, rh_order, for_rebalance=False):
        super().record_order(rh_order, for_rebalance)

        # TODO - rewrite the whole file as valid yaml, split files after X number of orders to keep file size low
        with open(self.historical_orders_file_path, 'a') as historical_orders_file:
            yaml.safe_dump({'order': rh_order}, historical_orders_file)

    # dump order state to file
    def save(self, silent=False):
        if not silent:
            self.print_metrics()

        with open(self.orders_file_path, 'w') as orders_file:
            yaml.safe_dump(
                {'orders': self.open_orders, 'metrics': self.metrics, 'terminal_quantity': self.terminal_quantity},
                orders_file
            )


# for testing
class InMemoryStateManager(BaseStateManager):
    def __init__(self, terminal_sell_quantity=None, terminal_buy_quantity=None):
        self.open_orders = None
        self.metrics = {}
        self.terminal_quantity = {OrderSide.BUY: terminal_buy_quantity, OrderSide.SELL: terminal_sell_quantity}

    def record_order(self, rh_order, for_rebalance=False):
        super().record_order(rh_order, for_rebalance)


# keeps track of the state of each tick for the purposes of visual plotting of data
class GraphingStateManager(InMemoryStateManager):
    def __init__(self):
        super().__init__()
        self.all_tick_data = []

    def record_base_metrics(self, coin_price, holdings, buying_power):
        super().record_base_metrics(coin_price, holdings, buying_power)
        self.all_tick_data.append({
            'coin_price': coin_price,
            'holdings': holdings,
            'buying_power': buying_power,
            'account_value': (holdings * coin_price) + buying_power,
            'sell_limit': self.open_orders[OrderSide.SELL][
                'price'] if self.open_orders and OrderSide.SELL in self.open_orders else None,
            'buy_limit': self.open_orders[OrderSide.BUY][
                'price'] if self.open_orders and OrderSide.BUY in self.open_orders else None
        })

    def record_order(self, rh_order, for_rebalance=False):
        super().record_order(rh_order, for_rebalance)
        self.all_tick_data[-1]['rebalance'] = for_rebalance
        self.all_tick_data[-1]['filled_order'] = rh_order
