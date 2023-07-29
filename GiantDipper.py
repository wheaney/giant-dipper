from datetime import datetime
from os.path import exists
from sys import argv

import yaml

from OrderManager import OrderManager
from OrderServices import RobinHoodOrderService, RealQuoteFakeOrderService
from StateManagers import FileStateManager
from RobinHoodAuth import robinhood_auth

if len(argv) > 1 and exists(argv[1]):
    with open(argv[1]) as configuration_file:
        configuration = yaml.safe_load(configuration_file)
        if configuration:
            service_config = configuration.get('service')
            state_config = configuration.get('state')
            order_manager_config = configuration.get('order_manager')

            if service_config and state_config and order_manager_config:
                robinhood_auth()

                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                state = FileStateManager(state_config['orders_file'], state_config['historical_orders_file'])

                manager = OrderManager(
                    order_service=RobinHoodOrderService(service_config['symbol']),
                    state_manager=state,
                    price_increment_ratio=order_manager_config['price_increment_ratio'],
                    order_quantity_ratio=order_manager_config['order_holdings_threshold'] /
                                         order_manager_config['quantity_threshold_ratio'],
                    order_holdings_threshold=order_manager_config['order_holdings_threshold'],
                    window_duration=order_manager_config.get('window_duration'),
                    window_factor=order_manager_config.get('window_factor', 1),
                    rebalance_interval=order_manager_config.get('rebalance_interval'),
                    rebalance_threshold=order_manager_config.get('rebalance_threshold')
                )
                manager.run()
                state.save()

                # optional comparison configs allow for using a fake order state with real quotes and account holdings
                # to test out alternative configurations
                for comparison_config in configuration.get('comparisons', []):
                    comparison_service_config = comparison_config.get('service')
                    comparison_state_config = comparison_config.get('state')
                    comparison_order_manager_config = comparison_config.get('order_manager')

                    if comparison_service_config and comparison_state_config and comparison_order_manager_config:
                        comparison_state = FileStateManager(comparison_state_config['orders_file'],
                                                            comparison_state_config['historical_orders_file'])

                        # comparison can optionally specify its own symbol, otherwise fall back to the parent config
                        symbol = (comparison_service_config or {}).get('symbol', service_config['symbol'])

                        comparison_service = RealQuoteFakeOrderService(symbol, comparison_service_config['state_file'])

                        comparison_manager = OrderManager(
                            order_service=comparison_service,
                            state_manager=comparison_state,
                            price_increment_ratio=comparison_order_manager_config['price_increment_ratio'],
                            order_quantity_ratio=comparison_order_manager_config['order_holdings_threshold'] /
                                                 comparison_order_manager_config['quantity_threshold_ratio'],
                            order_holdings_threshold=comparison_order_manager_config['order_holdings_threshold'],
                            window_duration=comparison_order_manager_config.get('window_duration'),
                            window_factor=comparison_order_manager_config.get('window_factor', 1),
                            rebalance_interval=comparison_order_manager_config.get('rebalance_interval'),
                            rebalance_threshold=comparison_order_manager_config.get('rebalance_threshold'),
                            silent=True
                        )
                        comparison_manager.run()
                        comparison_service.save()
                        comparison_state.save(silent=True)

                print("")
