import csv
from datetime import datetime
from os.path import exists
from time import sleep

import robin_stocks
import yaml

from giant_dipper.OrderManager import BUY_ORDER_COLLAR, SELL_ORDER_COLLAR
from giant_dipper.OrderSides import OrderSide
from giant_dipper.OrderStatuses import OPEN_ORDER_STATUSES, OrderStatus


# All calls delegate to RobinHood APIs. if disallow_orders is set, an Exception will be raised if any attempts to
# cancel or create orders are made through this class, useful for implementations that want to use real account
# or quote data without accidentally creating orders.
class RobinHoodOrderService:
    def __init__(self, symbol, disallow_orders=False):
        self.symbol = symbol
        self.disallow_orders = disallow_orders

    def get_quote(self):
        return float(robin_stocks.robinhood.get_crypto_quote(self.symbol)['mark_price'])

    def get_order_info(self, order_id):
        order = robin_stocks.robinhood.get_crypto_order_info(order_id)
        order['last_transaction_at'] = datetime.fromisoformat(order['last_transaction_at'])

        return order

    def get_holdings(self):
        for position in robin_stocks.robinhood.get_crypto_positions():
            if position['currency']['code'] == self.symbol:
                return round(float(position['quantity']))

        return 0

    def get_buying_power(self):
        return float(robin_stocks.robinhood.account.load_account_profile()['portfolio_cash'])

    def __check_order_allowed(self, call_name):
        if self.disallow_orders:
            raise Exception("RobinHoodOrderService.{} call not allowed".format(call_name))

    def cancel_order(self, order_id):
        self.__check_order_allowed('cancel_order')
        robin_stocks.robinhood.cancel_crypto_order(order_id)

        order = robin_stocks.robinhood.get_crypto_order_info(order_id)
        while order['state'] != OrderStatus.CANCELLED:
            sleep(1)
            order = robin_stocks.robinhood.get_crypto_order_info(order_id)

        return order

    def order_sell_limit(self, quantity, limit_price):
        self.__check_order_allowed('order_sell_limit')
        return robin_stocks.robinhood.order_sell_crypto_limit(self.symbol, quantity, limit_price)

    def order_sell(self, quantity):
        self.__check_order_allowed('order_sell')
        return self.__wait_for_order_complete(
            robin_stocks.robinhood.order_sell_crypto_by_quantity(self.symbol, quantity))

    def order_buy_limit(self, quantity, limit_price):
        self.__check_order_allowed('order_buy_limit')
        return robin_stocks.robinhood.order_buy_crypto_limit(self.symbol, quantity, limit_price)

    def order_buy(self, buy_value):
        self.__check_order_allowed('order_buy')
        return self.__wait_for_order_complete(
            robin_stocks.robinhood.order_buy_crypto_by_price(self.symbol, buy_value))

    def __wait_for_order_complete(self, order):
        while 'id' in order and order['state'] in OPEN_ORDER_STATUSES:
            sleep(1)
            order = robin_stocks.robinhood.get_crypto_order_info(order['id'])

        return order


# all account state values (including outstanding buy/sell orders) are stored locally
class LocalAccountStateOrderService:
    DEFAULT_START_ACCOUNT_VALUE = 10000

    def __init__(self, buy_order=None, sell_order=None, next_order_id=0, buying_power=None, holdings=None):
        self.buy_order = buy_order
        self.sell_order = sell_order
        self.next_order_id = next_order_id
        self.buying_power = buying_power
        self.holdings = holdings

    def get_holdings(self):
        return self.holdings

    def get_buying_power(self):
        return self.buying_power

    def get_order_info(self, order_id):
        if self.buy_order and self.buy_order['id'] == order_id:
            return self.buy_order
        elif self.sell_order and self.sell_order['id'] == order_id:
            return self.sell_order

        return None

    def cancel_order(self, order_id):
        order = self.get_order_info(order_id)
        if order and order['state'] in OPEN_ORDER_STATUSES:
            order['state'] = OrderStatus.CANCELLED

    def order_sell_limit(self, quantity, price):
        self._check_holdings(quantity)

        self.sell_order = self._create_next_order(OrderSide.SELL, price, quantity)

        return self.sell_order

    def order_sell(self, quantity):
        sell_price = self.get_quote() * SELL_ORDER_COLLAR
        sell_value = sell_price * quantity
        self._check_and_decrement_holdings(quantity)
        self.buying_power += sell_value

        order = self._create_next_order(OrderSide.SELL, sell_price, quantity)
        order['rounded_executed_notional'] = sell_value
        order['average_price'] = sell_price
        order['state'] = OrderStatus.FILLED
        order['last_transaction_at'] = self._get_date()

        return order

    def order_buy_limit(self, quantity, price):
        self._check_buying_power(price * quantity)

        self.buy_order = self._create_next_order(OrderSide.BUY, price, quantity)

        return self.buy_order

    def order_buy(self, buy_value):
        buy_price = self.get_quote() * BUY_ORDER_COLLAR
        quantity = buy_value / buy_price
        self._check_and_decrement_buying_power(buy_value)
        self.holdings += quantity

        order = self._create_next_order(OrderSide.BUY, buy_price, quantity)
        order['rounded_executed_notional'] = buy_value
        order['average_price'] = buy_price
        order['state'] = OrderStatus.FILLED
        order['last_transaction_at'] = self._get_date()

        return order

    def _create_next_order(self, side, price, quantity):
        self.next_order_id += 1
        return {
            'id': self.next_order_id,
            'quantity': quantity,
            'price': price,
            'state': OrderStatus.OPEN,
            'side': side
        }

    # checks current buy/sell orders against the current low/high prices and fills the orders as necessary
    def _check_orders(self, low, high):
        order = self.buy_order
        if order and order['state'] in OPEN_ORDER_STATUSES:
            price = order['price']
            quantity = order['quantity']
            if price > (low * BUY_ORDER_COLLAR):
                order['state'] = OrderStatus.FILLED
                order['last_transaction_at'] = self._get_date()
                order['average_price'] = price
                order['rounded_executed_notional'] = price * quantity
                self._check_and_decrement_buying_power(order['rounded_executed_notional'])
                self.holdings += quantity

        order = self.sell_order
        if order and order['state'] in OPEN_ORDER_STATUSES:
            price = order['price']
            quantity = order['quantity']
            if price < (high * SELL_ORDER_COLLAR):
                order['state'] = OrderStatus.FILLED
                order['last_transaction_at'] = self._get_date()
                order['average_price'] = price
                order['rounded_executed_notional'] = price * quantity
                self._check_and_decrement_holdings(quantity)
                self.buying_power += order['rounded_executed_notional']

    def _check_holdings(self, quantity):
        if quantity > self.holdings:
            raise Exception('Attempting to sell {} with only {} available'.format(quantity, self.holdings))

    # decrements holdings by the specified amount, raises an exception if this will result in a negative
    def _check_and_decrement_holdings(self, quantity):
        self._check_holdings(quantity)
        self.holdings -= quantity

    def _check_buying_power(self, value):
        if value > self.buying_power:
            raise Exception('Attempting to buy ${} with only ${} available'.format(value, self.buying_power))

    # decrements buying_power by the specified amount, raises an exception if this will result in a negative
    def _check_and_decrement_buying_power(self, value):
        self._check_buying_power(value)
        self.buying_power -= value


# Use a CSV file to provide quotes w/ local account state
#
# Required CSV spreadsheet headings:
# * "date" - date of quote, with minute granularity, in the format of csv_datetime_format
# * "open", "low", and "high" - opening, low, and high prices for the given time increment
class CSVFileOrderService(LocalAccountStateOrderService):
    # cache this as a static variable in the class
    all_minutes = None

    def __init__(self, csv_file, minute_increments, cash_holdings_percentage, csv_datetime_format, start_minute=0):
        if not CSVFileOrderService.all_minutes:
            with open(csv_file) as file:
                reader = csv.DictReader(file)
                print("Caching values from the file {}".format(csv_file))

                CSVFileOrderService.all_minutes = []
                while True:
                    next_minute = next(reader, None)
                    if not next_minute:
                        break

                    CSVFileOrderService.all_minutes.append(next_minute)

                print("Done caching CSV values")

        self.minute_increments = minute_increments
        self.csv_datetime_format = csv_datetime_format
        self.minute_index = start_minute
        self.current_minute = CSVFileOrderService.all_minutes[self.minute_index]
        buying_power = round(cash_holdings_percentage * self.DEFAULT_START_ACCOUNT_VALUE, 2)
        super().__init__(
            buying_power=buying_power,
            holdings=round((self.DEFAULT_START_ACCOUNT_VALUE - buying_power) / self.get_quote())
        )

    def get_quote(self):
        return float(self.current_minute['open'])

    def _get_date(self):
        return self.current_minute['date']

    # move forward by minute_increments, return true if there are still more rows from the CSV
    def tick(self):
        for i in range(self.minute_increments):
            super()._check_orders(
                low=float(self.current_minute['low']),
                high=float(self.current_minute['high'])
            )

            self.minute_index += 1
            if len(CSVFileOrderService.all_minutes) == self.minute_index:
                return False

            self.current_minute = CSVFileOrderService.all_minutes[self.minute_index]

        return True


# combine real quotes, holding, and buying power values from RH with local account storage
class RealQuoteFakeOrderService(LocalAccountStateOrderService, RobinHoodOrderService):
    def __init__(self, symbol, state_file_path):
        RobinHoodOrderService.__init__(self, symbol, disallow_orders=True)
        self.current_quote = None
        self.state_file_path = state_file_path

        if exists(state_file_path):
            with open(state_file_path) as state_file:
                state = yaml.safe_load(state_file)
                LocalAccountStateOrderService.__init__(
                    self,
                    holdings=state['holdings'],
                    buying_power=state['buying_power'],
                    buy_order=state['buy_order'],
                    sell_order=state['sell_order'],
                    next_order_id=state['next_order_id']
                )
        else:
            LocalAccountStateOrderService.__init__(
                self,
                holdings=RobinHoodOrderService.get_holdings(self),
                buying_power=RobinHoodOrderService.get_buying_power(self),
                buy_order=None,
                sell_order=None,
                next_order_id=0
            )

        LocalAccountStateOrderService._check_orders(
            self=self,
            low=self.get_quote(),
            high=self.get_quote()
        )

    # retrieve quote from RH; cache it since this is used frequently
    def get_quote(self):
        self.current_quote = self.current_quote or RobinHoodOrderService.get_quote(self)

        return self.current_quote

    def save(self):
        with open(self.state_file_path, 'w') as state_file:
            yaml.safe_dump(
                {
                    'holdings': self.holdings,
                    'buying_power': self.buying_power,
                    'buy_order': self.buy_order,
                    'sell_order': self.sell_order,
                    'next_order_id': self.next_order_id
                }, state_file)

    def _create_next_order(self, side, price, quantity):
        self.next_order_id += 1
        return {
            'id': self.next_order_id,
            'quantity': quantity,
            'price': price,
            'state': OrderStatus.OPEN,
            'side': side
        }

    def _get_date(self):
        return datetime.now()
