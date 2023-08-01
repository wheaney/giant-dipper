# Giant Dipper - Automated Trading Algorithm for Volatile Assets

## Disclaimer

This algorithm is designed for automated trading of assets with high volatility and risk. If you choose to use this algorithm, you must accept the possibility of significant financial losses. The maintainers of this repository are not responsible for any losses incurred (but feel free to send any gains our way!).

## Background

I began to watch Dogecoin more closely after it went to the moon and back in 2021, and I noticed that it frequently moves by 5-10% in a day, but still tends to hover around the same prices for a while. I thought, "man, anyone trading on these small daily ups-and-downs could be making bank!" but didn't do anything about it, still just keeping an eye on the daily movements. After months of this, I figured it was time to take the plunge, set some money aside that I wouldn't mind losing, and play around with writing my own algorithm meant to take advantage of these frequent but significant movements. 

This algorithm is best suited for assets that exhibit the following characteristics:

* **Very volatile short-term activity:** Frequent and significant short-term price movements.
* **Fairly stable for long periods:** The asset tends to maintain a relatively stable price over longer periods, with significant ups followed by downs and vice versa.

I've personally found Dogecoin to be an interesting asset for this because its supply is uncapped and still growing pretty rapidly, thus diluting the current pool of coins which has tended to keep value steady despite occasional spikes in interest. On the flip side, the meme-coin aspect of it still manages to create a lot of volatility.

## How It Works

### Part 1 - Choosing Buy/Sell Percentage

To start, you select a percentage value, *X*, which determines the price thresholds for buying and selling. When the price increases by *X* percent, the algorithm sells some coins, and when it decreases by the inverse percentage, it buys more coins. Using the inverse percentage ensures that the up/down steps of the target prices remain consistent and predictable.

**Example:** If *X* is 5% and the coin is worth $1, the algorithm will sell coins at increments of 105%: $1.05, $1.1025, $1.157625, and so on. For buying, it will use the inverse increments, where 100/105 is approximately 95.23%: $0.9523, $0.9070, $0.8638, and so on. When we first run the code, it would set limit buy and sell orders for $0.9523 and $1.05, respectively, then wait. If our initial sell price of $1.05 is hit, the algorithm will cancel the first limit buy order, and set new buy and sell orders for $1.1025 and $1, respectively. If the $1 buy order hits, we've now made profits that are equal to sell dollar value minus buy dollar value.

### Part 2 - Determining Quantities

To decide how many coins the algorithm buys and sells, you need to set two percentage values, *Y* and *Z*. *Y* represents how much of your total account value (money plus crypto) you are willing to use for any single buy or sell order. To prevent overcommitting your assets, *Z* sets a cap on the percentage of your total money or crypto that can be used in a single order.

**Example:** Let's say *X* is 5%, the coin is worth $1, and I decide that I want each trade to buy or sell 10% of my account value (*Y*). If my account has $950 and only 50 coins, then my total account value is $1000, so my next sell order should be for 10%, or $100 worth of coins, which is 100 coins. But since I only have 50 and I don't want to completely sell out of them, I set a percentage *Z* that tells the algorithm to never exceed a certain percentage of my money or crypto. If I set *Z* to 50%, then the algorithm will create a limit sell at $1.05 for half of my coins, only 25, and a limit buy for $100.

To prevent the inverse steps from becoming unequal due to these caps, the next buy quantity would be proportional to the previous capped sell price. So if the 50% cap was hit on my previous order and I only sold 25 coins (instead of 100), then the next buy order (that would reverse that sell) will only be allowed to use roughly those same $25 to determine the quantity. If this safeguard weren't in place, then the up/down steps would become imbalanced and potentially set us up for losses (i.e. causing a buy-high-sell-low scenario or vice versa).

### Part 3 - Centering (Optional)

All of the above works great, if you don't have bad timing. Let's say I started the algorithm when Dogecoin was peaking at around 70 cents. By the time it began to settle around 10 cents, the algorithm would have hit buy after buy after buy order until it had used all, or nearly all, of my money, even with the *Z* percentage set to something reasonable. This is an extreme example, but highlights a flaw: the algorithm works best when it can buy or sell the full *Y* percentage every time. The sweet spot is when 50% of my account is money, and 50% is crypto. If you find the price where the algorithm would achieve this balance, this is it's "center" price. Unfortunately, this center is arbitrarily determined by when you chose to start the algorithm and what the balance of money to crypto was in your account when you started it. Ideally, the algorithm would readjust the center if bigger long-term movements in the crypto price meant that we're no longer near that sweet spot.

This is where the concept of a rebalance threshold, *W*, comes in. If sells outnumber buys, or vice versa, to the point where the account balance is thrown way off to one side (way more money than crypto, or vice versa), *W* can be set to represent how big of an imbalance triggers a "rebalance" of funds to holdings. Once this is triggered, the algorithm will use another value called the rebalance interval, *V*, to help it determine what crypto price it should recenter itself around. *V* is the number of "ticks" -- how many times the algorithm is run, at whatever time interval you prefer -- it will use to gather an average crypto price, and after this interval it will buy or sell to achieve a 50/50 balance of money to crypto centered around that price. Now the "center" is no longer arbitrarily determined by the original starting price or balance of the account.

**Example:** Let's say our account has $750 and 250 coins at a price of $1, and *Y* is 10% so the next buy and sell orders will be for $100 and 100 coins each. If our *W* is 60%, this means that the *difference* in percentages of crypto to money shouldn't exceed 60% -- in other words, 80% money and 20% crypto, or vice versa -- then if our next limit sell order hits, we'll suddenly have around 150 coins and $850 (not exactly since the crypto price had to change to hit the limit). This is going to be roughly a 70% difference (85% minus 15%), so our threshold is hit. If our algorithm runs every minute, then it will wait *V* minutes and average the crypto price during that time. Let's say the average comes out to $1, it will then buy about $350 of coins so that our account is balance at around 500 coins and $500.

#### Risk of loss from automated rebalancing

Note that rebalancing will often realize a loss, because the algorithm is built around the hope that the crypto price doesn't make big, sustained movements. So when it *does* make a movement that jeopardizes the algorithm's ability to make money and requires a rebalance, it will usually trigger a buy-high-sell-low or sell-low-buy-high scenario. While this is obviously bad in the moment, my testing on historical data has shown rebalancing to be a net-benefit. In other words, moving the "center" so that our next buy/sell orders can operate at our desired quantities will usually outweigh the loss that's realized by the act of rebalancing. Sometimes a huge spike results in a large move that's followed quickly by an opposite move of nearly the same magnitude; in the case that this triggers a rebalance on both ends of the spike, you'll be registering twice the loss. Again, running with a well configured algorithm against historical data still tends to yield gains, but this is still a risk you have to contend with.

You can choose to leave the rebalance configuration values unset. This leaves you open to running out of money or crypto if a large movement is sustained (e.g. the price goes way up and never comes down), and making no money during that sustained time period. You could also choose to manually rebalance your account in these scenarios, so you'll have to weigh the prospect of automating this activity vs doing it yourself (or not doing it at all).

### Part 4 - Windows (Optional)

When I first developed this algorithm, I tried to account for the rarer large movements by adding the concept of a growing and shrinking price "window" for some time after a limit order hits. What if Elon renamed Twitter to Dogebank and the price of Dogecoin goes up 10x in 5 minutes? The algorithm as I've described it already would sell at each *X*% interval until it ran out of crypto. But what if the value of *X* increased every time a limit order was hit, so that instead of my next sell price being 5% higher, it was instead 10% higher? This would mean bigger profits on bigger movements. And the window would increase with each successive sell, so it would go roughly from 5% to 10% then to 15%, so if there was some sustained short-term movement during our window we would continue to grow the window size. Then a countdown clock begins after each growing of the window that determines when to shrink the window back down (the "window duration"). Note also that increasing the window size will increase the order quantities; since a "window size" of 1 will result in an order that applies *X* twice, that order takes us two "steps" ahead and thus should also use two steps worth of quantity. This prevents the "center" from moving and some money-losing scenarios caused by imbalanced orders.

What I found when running this against historical data was that it wasn't as useful as it sounds, and it doesn't completely mitigate the risk of being priced out when your move too far from your current center, which the rebalancing behavior in Part 3 mitigates. So, I've personally found rebalancing to be an effective tool, while the most successful simulations always resulted in a basically non-existant window configuration. It could be that both are effective, but they work against each other and rebalancing is slightly more effective. But the code for it is still here and you can play around with it.

**Example:** The "window factor" determines how many steps each window increment accounts for. Let's say *X* is 5% again. If a sell order hits, our window size goes from 0 to 1 and our window factor is 1, then the algorithm will apply *X* twice to the next sell price (window size times window factor, plus 1). So if the sell hit at $1, then applying the 5% price increment twice gives us our next sell price of $1.1025, effectively skipping the $1.05 step that would normally have been next. If $1.1025 gets hit, then the window size increments again, from 1 to 2, and we'll apply *X* three times to the next price increment, resulting in our next sell price being about $1.2763. If things calm down and the algorithm waits for the"window duration" number of minutes without another sell, then the window size will decrement from 2 back to 1, it will cancel the current limit sell order and replace it with one that only applies *X* twice at about $1.2155.

Window factor can be a decimal, so the steps aren't necessarily as clean as the above example.

## Getting Started

Before using the algorithm, you need to set the configuration values described in the "How It Works" sections above. 

Maybe you just want to do this by intuition, and you can certainly be successful this way, but I found that my intuition was way off of what the *ideal*, highest-earning values actually ended up being. For me, finding these values meant running tens of thousand of simulations on historical data. This will require finding a source of historical Dogecoin data, ideally by-the-minute granularity in CSV form. Then you can use a library -- I used Optuna -- to tune each of the variables and use the `CSVFileOrderService` with the data you collected above. Once you feel confident that you've tuned the values to your liking, you're ready to go.

To use this algorithm:

1. Install python 3 and Pipenv by running `pip install pipenv --user` after installing python
2. Check out the code, change into the `giant-dipper` directory and run `pipenv install`
3. Set up your configuration YAML in the code directory. See the example below.
4. Set up your credentials YAML in the code directory. See the example below.
5. Take a deep breath.
6. Set up a cronjob or some other trigger on a time interval
    1. The crontab config to run this every minute would look like: `* * * * * cd /path/to/giant-dipper && pipenv run python GiantDipper.py configuration.yml >> ~/giant_dipper_cron`
        1. This will write output to the file at `~/giant_dipper_cron`, you can use that to track orders and metrics.

## Example Configuration YAML

**Please note: The examples used here are for illustration purposes only and SHOULD NOT BE USED without careful consideration and customization for your specific situation.**

```yaml
service:
  symbol: "DOGE"
state:
  orders_file: "/path/to/orders.yml"
  historical_orders_file: "/path/to/historical_orders.yml"
order_manager:
  order_holdings_threshold: 0.1
  quantity_threshold_ratio: 1.5
  price_increment_ratio: 1.05
  rebalance_interval: 100
  rebalance_threshold: 0.75
```

The `state` files store the current state of the algorithm between runs. They should point to files that don't yet exist and they will get created on the first run.

The `order_manager` values are what configure the algorithm per the **How it works** section above. They're unfortunately a little confusing and could use some fixing:
* `order_holdings_threshold` - described as *Z* in Part 2. This is the cap on how much the algorithm can use for a single order of either money or crypto. The example value of `0.1` means it will never sell more than 10% of your coins nor spend more than 10% of your money in ANY SINGLE ORDER.
* `quantity_threshold_ratio` - used to compute *Y* as described in Part 2. The value you configure here is the ratio determined by computing *Z* divided by *Y*. Since *Z* only makes sense if it's bigger than *Y*, then this value should always be a decimal greater than 1. This is confusing and should be reworked (it was ideal for my own parameter tuning).
* `price_increment_ratio` - described as *X* in Part 2. This determines the price targets for the next buy and sell orders. A value of 5% would be represented as 1.05. This should always be greater than 1.
* `rebalance_interval` - described as *V* in Part 3. This is the number of "ticks" to use to compute the average price for rebalancing. If your cronjob runs in 1 minute intervals, then this value is the wait time in minutes, as an integer.
* `rebalance_threshold` - described as *W* in Part 3. This is the delta between percentage of money vs crypto that will trigger a rebalance if exceeded. A value of 50% should be represented as 0.5.
* `window_factor` - described in Part 4. This determines the power to raise the `price_increment_ratio` to when the "window size" is incremented after an order is hit; where the formula is `price_increment_ratio^((window_factor * window_size) +1)`. This can be any decimal greater than zero. Windows are disabled and this value is ignored if `window_duration` is unset.
* `window_duration` - described in Part 4. This is the number of "ticks" that the algorithm will wait before decrementing the window size if no orders are hit, as an integer. Windows are disabled if this value is unset.

## Example Credentials YAML

I can't remember if Robinhood requires two-factor auth using an OTP provider. If so, you'll want to set up two-factor with an OTP app (e.g. Google Authenticator) and set the secret here. If two-factor isn't required and you don't want to set it up, just user/pass should work fine here.

This package is set up to allow the use of other brokerage APIs, but only Robinhood is implemented, so for now that's the only one this configuration supports too.

This file needs to be named `credentials.yml` and live in the same directory you're running the script from.

```yaml
robinhood:
  username: "your@email.com"
  password: "your-password"
  otp_secret: "your OTP secret"
```
