"""
Disclaimer

All investment strategies and investments involve risk of loss.
Nothing contained in this program, scripts, code or repositoy should be
construed as investment advice.Any reference to an investment's past or
potential performance is not, and should not be construed as, a recommendation
or as a guarantee of any specific outcome or profit.

By using this program you accept all liabilities,
and that no claims can be made against the developers,
or others connected with the program.
"""


# use for environment variables
import os

# use if needed to pass args to external modules
import sys

# used to create threads & dynamic loading of modules
import threading
import importlib

# used for directory handling
import glob

# Needed for colorful console output Install with: python3 -m pip install colorama (Mac/Linux) or pip install colorama (PC)
from colorama import init
init()

# needed for the binance API / websockets / Exception handling
from binance.client import Client
from binance.exceptions import BinanceAPIException

# used for dates
from datetime import date, datetime, timedelta
import time

# used to repeatedly execute the code
from itertools import count

# used to store trades and sell assets
import json

# Load helper modules
from helpers.parameters import (
    parse_args, load_config
)

# Load creds modules
from helpers.handle_creds import (
    load_correct_creds, test_api_key
)


# for colourful logging to the console
class txcolors:
    BUY = '\033[92m'
    WARNING = '\033[93m'
    SELL_LOSS = '\033[91m'
    SELL_PROFIT = '\033[32m'
    DIM = '\033[2m\033[35m'
    DEFAULT = '\033[39m'


# tracks profit/loss each session
global session_profit, unrealised_percent, unrealised_percent_delay
session_profit = 0
unrealised_percent = 0
unrealised_percent_delay = 0

global profit_history
try:
    profit_history
except NameError:
    profit_history = 0      # or some other default value.


# print with timestamps
old_out = sys.stdout
class St_ampe_dOut:
    """Stamped stdout."""
    nl = True
    def write(self, x):
        """Write function overloaded."""
        if x == '\n':
            old_out.write(x)
            self.nl = True
        elif self.nl:
            old_out.write(f'{txcolors.DIM}[{str(datetime.now().replace(microsecond=0))}]{txcolors.DEFAULT} {x}')
            self.nl = False
        else:
            old_out.write(x)

    def flush(self):
        pass

sys.stdout = St_ampe_dOut()

def is_fiat():
    # check if we are using a fiat as a base currency
    global hsp_head
    PAIR_WITH = parsed_config['trading_options']['PAIR_WITH']
    #list below is in the order that Binance displays them, apologies for not using ASC order
    fiats = ['USDT', 'BUSD', 'AUD', 'BRL', 'EUR', 'GBP', 'RUB', 'TRY', 'TUSD', 'USDC', 'PAX', 'BIDR', 'DAI', 'IDRT', 'UAH', 'NGN', 'VAI', 'BVND']

    if PAIR_WITH in fiats:
        return True
    else:
        return False

def decimals():
    # set number of decimals for reporting fractions
    if is_fiat():
        return 2
    else:
        return 8


def get_price(add_to_historical=True):
    '''Return the current price for all coins on binance'''

    global historical_prices, hsp_head

    initial_price = {}
    prices = client.get_all_tickers()

    for coin in prices:

        if CUSTOM_LIST:
            if any(item + PAIR_WITH == coin['symbol'] for item in tickers) and all(item not in coin['symbol'] for item in FIATS):
                initial_price[coin['symbol']] = { 'price': coin['price'], 'time': datetime.now()}
        else:
            if PAIR_WITH in coin['symbol'] and all(item not in coin['symbol'] for item in FIATS):
                initial_price[coin['symbol']] = { 'price': coin['price'], 'time': datetime.now()}

    if add_to_historical:
        hsp_head += 1

        if hsp_head == RECHECK_INTERVAL:
            hsp_head = 0

        historical_prices[hsp_head] = initial_price

    return initial_price


def wait_for_price():
    '''calls the initial price and ensures the correct amount of time has passed
    before reading the current price again'''

    global historical_prices, hsp_head, volatility_cooloff

    volatile_coins = {}
    externals = {}

    coins_up = 0
    coins_down = 0
    coins_unchanged = 0

    pause_bot()

    if historical_prices[hsp_head]['BNB' + PAIR_WITH]['time'] > datetime.now() - timedelta(minutes=float(TIME_DIFFERENCE / RECHECK_INTERVAL)):

        # sleep for exactly the amount of time required
        time.sleep((timedelta(minutes=float(TIME_DIFFERENCE / RECHECK_INTERVAL)) - (datetime.now() - historical_prices[hsp_head]['BNB' + PAIR_WITH]['time'])).total_seconds())

    balance_report()

    # retrieve latest prices
    get_price()

    # calculate the difference in prices
    for coin in historical_prices[hsp_head]:

        # minimum and maximum prices over time period
        min_price = min(historical_prices, key = lambda x: float("inf") if x is None else float(x[coin]['price']))
        max_price = max(historical_prices, key = lambda x: -1 if x is None else float(x[coin]['price']))

        threshold_check = (-1.0 if min_price[coin]['time'] > max_price[coin]['time'] else 1.0) * (float(max_price[coin]['price']) - float(min_price[coin]['price'])) / float(min_price[coin]['price']) * 100

        # each coin with higher gains than our CHANGE_IN_PRICE is added to the volatile_coins dict if less than TRADE_SLOTS is not reached.
        if threshold_check > CHANGE_IN_PRICE:
            coins_up +=1

            if coin not in volatility_cooloff:
                volatility_cooloff[coin] = datetime.now() - timedelta(minutes=TIME_DIFFERENCE)

            # only include coin as volatile if it hasn't been picked up in the last TIME_DIFFERENCE minutes already
            if datetime.now() >= volatility_cooloff[coin] + timedelta(minutes=TIME_DIFFERENCE):
                volatility_cooloff[coin] = datetime.now()

                if len(coins_bought) + len(volatile_coins) < TRADE_SLOTS or TRADE_SLOTS == 0:
                    volatile_coins[coin] = round(threshold_check, 3)
                    print(f"{coin} has gained {volatile_coins[coin]}% within the last {TIME_DIFFERENCE} minutes, calculating {QUANTITY} {PAIR_WITH} value of {coin} for purchase!")

                else:
                    print(f"{txcolors.WARNING}{coin} has gained {round(threshold_check, 3)}% within the last {TIME_DIFFERENCE} minutes, but you are using all available trade slots!{txcolors.DEFAULT}")

        elif threshold_check < CHANGE_IN_PRICE:
            coins_down +=1

        else:
            coins_unchanged +=1

    # Disabled until fix
    #print(f'Up: {coins_up} Down: {coins_down} Unchanged: {coins_unchanged}')

    # Here goes new code for external signalling
    externals = external_signals()
    exnumber = 0

    for excoin in externals:
        if excoin not in volatile_coins and excoin not in coins_bought and (len(coins_bought) + exnumber) < TRADE_SLOTS:
            volatile_coins[excoin] = 1
            exnumber +=1
            print(f"External signal received on {excoin}, calculating {QUANTITY} {PAIR_WITH} value of {excoin} for purchase!")

    return volatile_coins, len(volatile_coins), historical_prices[hsp_head]


def external_signals():
    external_list = {}
    signals = {}

    # check directory and load pairs from files into external_list
    signals = glob.glob("signals/*.exs")
    for filename in signals:
        for line in open(filename):
            symbol = line.strip()
            external_list[symbol] = symbol
        try:
            os.remove(filename)
        except:
            if DEBUG: print(f"{txcolors.WARNING}Could not remove external signalling file{txcolors.DEFAULT}")

    return external_list


def balance_report():
    global profit_history, unrealised_percent
    INVESTMENT_TOTAL = (QUANTITY * TRADE_SLOTS)
    CURRENT_EXPOSURE = (QUANTITY * len(coins_bought))
    TOTAL_GAINS = ((QUANTITY * session_profit) / 100)
    NEW_BALANCE = (INVESTMENT_TOTAL + TOTAL_GAINS)
    INVESTMENT_GAIN = (TOTAL_GAINS / INVESTMENT_TOTAL) * 100
    PROFIT_HISTORY = profit_history
    # truncating some of the above values to the correct decimal places before printing
    INVESTMENT_TOTAL  = round(INVESTMENT_TOTAL,decimals() )
    CURRENT_EXPOSURE = round(CURRENT_EXPOSURE,decimals() )

    if len(coins_bought) > 0:
        UNREALISED_PERCENT = unrealised_percent/len(coins_bought)
    else:
        UNREALISED_PERCENT = 0

    print(f'Trade slots: {len(coins_bought)}/{TRADE_SLOTS} ({float(CURRENT_EXPOSURE):g}/{float(INVESTMENT_TOTAL):g}{PAIR_WITH}) | Open trades: {UNREALISED_PERCENT:.2f}% | Closed trades: {session_profit:.2f}% (all time: {PROFIT_HISTORY:.2f}%) | Session profit: {INVESTMENT_GAIN:.2f}% ({TOTAL_GAINS:.{decimals()}f}{PAIR_WITH})')
    unrealised_percent_calc()
    return


def pause_bot():
    '''Pause the script when external indicators detect a bearish trend in the market'''
    global bot_paused, session_profit, hsp_head

    # start counting for how long the bot has been paused
    start_time = time.perf_counter()

    while os.path.isfile("signals/paused.exc"):

        if bot_paused == False:
            print(f"{txcolors.WARNING}Buying paused due to negative market conditions, stop loss and take profit will continue to work...{txcolors.DEFAULT}")
            bot_paused = True

        # Sell function needs to work even while paused
        coins_sold = sell_coins()
        remove_from_portfolio(coins_sold)
        get_price(True)

        # pausing here
        if hsp_head == 1: print(f"Paused...Session profit:{session_profit:.2f}% Est: {(QUANTITY * session_profit)/100:.{decimals()}f} {PAIR_WITH}")
        time.sleep((TIME_DIFFERENCE * 60) / RECHECK_INTERVAL)

    else:
        # stop counting the pause time
        stop_time = time.perf_counter()
        time_elapsed = timedelta(seconds=int(stop_time-start_time))

        # resume the bot and ser pause_bot to False
        if  bot_paused == True:
            print(f"{txcolors.WARNING}Resuming buying due to positive market conditions, total sleep time: {time_elapsed}{txcolors.DEFAULT}")
            bot_paused = False

    return


def convert_volume():
    '''Converts the volume given in QUANTITY from USDT to the each coin's volume'''

    volatile_coins, number_of_coins, last_price = wait_for_price()
    lot_size = {}
    volume = {}

    for coin in volatile_coins:

        # Find the correct step size for each coin
        # max accuracy for BTC for example is 6 decimal points
        # while XRP is only 1
        try:
            info = client.get_symbol_info(coin)
            step_size = info['filters'][2]['stepSize']
            lot_size[coin] = step_size.index('1') - 1

            if lot_size[coin] < 0:
                lot_size[coin] = 0

        except:
            pass

        # calculate the volume in coin from QUANTITY in PAIR_WITH (default)
        volume[coin] = float(QUANTITY / float(last_price[coin]['price']))

        # define the volume with the correct step size
        if coin not in lot_size:
            volume[coin] = float('{:.1f}'.format(volume[coin]))

        else:
            # if lot size has 0 decimal points, make the volume an integer
            if lot_size[coin] == 0:
                volume[coin] = int(volume[coin])
            else:
                volume[coin] = float('{:.{}f}'.format(volume[coin], lot_size[coin]))

    return volume, last_price


def test_order_id():
    import random
    """returns a fake order id by hashing the current time"""
    test_order_id_number = random.randint(100000000,999999999)
    return test_order_id_number

def buy():
    '''Place Buy market orders for each volatile coin found'''
    global test_order_id
    volume, last_price = convert_volume()
    orders = {}

    for coin in volume:

        print(f"{txcolors.BUY}Preparing to buy {volume[coin]} {coin}{txcolors.DEFAULT}")

        if TEST_MODE:
            orders[coin] = [{
                'symbol': coin,
                'orderId': test_order_id(),
                'time': datetime.now().timestamp()
            }]

            # Log trade
            write_log(f"Buy : {volume[coin]} {coin} - {last_price[coin]['price']}")

            continue

        # try to create a real order if the test orders did not raise an exception
        try:
            buy_limit = client.create_order(
                symbol = coin,
                side = 'BUY',
                type = 'MARKET',
                quantity = volume[coin]
            )


        # error handling here in case position cannot be placed
        except Exception as e:
            print(e)

        # run the else block if the position has been placed and return order info
        else:
            orders[coin] = client.get_all_orders(symbol=coin, limit=99)

            # binance sometimes returns an empty list, the code will wait here until binance returns the order
            while orders[coin] == []:
                print('Binance is being slow in returning the order, calling the API again...')

                orders[coin] = client.get_all_orders(symbol=coin, limit=99)
                time.sleep(1)

            else:
                print('Order returned, saving order to file..')

                # Log trade
                write_log(f"Buy : {volume[coin]} {coin} - {last_price[coin]['price']}")


    return orders, last_price, volume


def sell_coins():
    '''sell coins that have reached the STOP LOSS or TAKE PROFIT threshold'''
    global hsp_head, session_profit, profit_history,coin_order_id
    last_price = get_price(False) # don't populate rolling window
    #last_price = get_price(add_to_historical=True) # don't populate rolling window
    coins_sold = {}

    for coin in list(coins_bought):


        # define stop loss and take profit
        TP = float(coins_bought[coin]['bought_at']) + (float(coins_bought[coin]['bought_at']) * coins_bought[coin]['take_profit']) / 100
        SL = float(coins_bought[coin]['bought_at']) + (float(coins_bought[coin]['bought_at']) * coins_bought[coin]['stop_loss']) / 100

        LastPrice = float(last_price[coin]['price'])
        sellFee = (coins_bought[coin]['volume'] * LastPrice) * (TRADING_FEE/100)
        BuyPrice = float(coins_bought[coin]['bought_at'])
        buyFee = (coins_bought[coin]['volume'] * BuyPrice) * (TRADING_FEE/100)
        PriceChange = float((LastPrice - BuyPrice) / BuyPrice * 100)

        # check that the price is above the take profit and readjust SL and TP accordingly if trialing stop loss used
        if LastPrice > TP and USE_TRAILING_STOP_LOSS:

            # increasing TP by TRAILING_TAKE_PROFIT (essentially next time to readjust SL)
            coins_bought[coin]['take_profit'] = PriceChange + TRAILING_TAKE_PROFIT
            coins_bought[coin]['stop_loss'] = coins_bought[coin]['take_profit'] - TRAILING_STOP_LOSS
            if DEBUG: print(f"{coin} TP reached, adjusting TP {coins_bought[coin]['take_profit']:.{decimals()}f}  and SL {coins_bought[coin]['stop_loss']:.{decimals()}f} accordingly to lock-in profit")
            continue

        # check that the price is below the stop loss or above take profit (if trailing stop loss not used) and sell if this is the case
        if LastPrice < SL or LastPrice > TP and not USE_TRAILING_STOP_LOSS:
            print(f"{txcolors.SELL_PROFIT if PriceChange >= 0. else txcolors.SELL_LOSS}TP or SL reached, selling {coins_bought[coin]['volume']} {coin} - {float(BuyPrice):g} - {float(LastPrice):g} : {PriceChange-(buyFee+sellFee):.2f}% Est: {(QUANTITY*(PriceChange-(buyFee+sellFee)))/100:.{decimals()}f} {PAIR_WITH}{txcolors.DEFAULT}")

#             if coins_bought[coin]['orderid'] is coin_order_id:
#                 print(f"this coin has an order ID of {coins_bought[coin]['orderid']}")

            # try to create a real order
            try:
                if not TEST_MODE:
                    sell_coins_limit = client.create_order(
                        symbol = coin,
                        side = 'SELL',
                        type = 'MARKET',
                        quantity = coins_bought[coin]['volume']
                    )

            # error handling here in case position cannot be placed
            except Exception as e:
                print(e)

            # run the else block if coin has been sold and create a dict for each coin sold
            else:
#                 coins_sold[coin]['orderid'] = coins_bought[coin]['orderid']
                coins_sold[coin] = coins_bought[coin]
#                 print(f"{coins_sold[coin]}")
                # coins_sold[coin] = coins_bought[coin]['orderid']

                # prevent system from buying this coin for the next TIME_DIFFERENCE minutes
                volatility_cooloff[coin] = datetime.now()

                # Log trade
                profit = ((LastPrice - BuyPrice) * coins_sold[coin]['volume']) * (1-(buyFee + sellFee))
                write_log(f"Sell: {coins_sold[coin]['volume']} {coin} - {BuyPrice} - {LastPrice} Profit: {profit:.{decimals()}f} {PAIR_WITH} ({PriceChange-(buyFee+sellFee):.2f}%)")
                session_profit = session_profit + (PriceChange-(buyFee+sellFee))
                profit_history = profit_history + (PriceChange-(buyFee+sellFee))

            continue

        # no action; print once every TIME_DIFFERENCE
        if hsp_head == 1:
            if len(coins_bought) > 0:
                print(f"Holding {coin} - Price: {BuyPrice}, Now: {LastPrice}, P/L: {txcolors.SELL_PROFIT if PriceChange >= 0. else txcolors.SELL_LOSS}{PriceChange-(buyFee+sellFee):.2f}% ({(QUANTITY*(PriceChange-(buyFee+sellFee)))/100:.{decimals()}f} {PAIR_WITH}{txcolors.DEFAULT})")

    if hsp_head == 1 and len(coins_bought) == 0: print(f"No trade slots are currently in use")

    return coins_sold
#     return coin_order_id


def update_portfolio(orders, last_price, volume):
    '''add every coin bought to our portfolio for tracking/selling later'''
    global profit_history

#     print(orders)
    for coin in orders:

        coins_bought[coin] = {
            'symbol': orders[coin][0]['symbol'],
            'orderid': orders[coin][0]['orderId'],
            'timestamp': orders[coin][0]['time'],
            'bought_at': last_price[coin]['price'],
            'volume': volume[coin],
            'stop_loss': -STOP_LOSS,
            'take_profit': TAKE_PROFIT,
            }

        # save the coins in a json file in the same directory
        with open(coins_bought_file_path, 'w') as file:
            json.dump(coins_bought, file, indent=4)

        #save session info for through session portability
        with open(profit_history_file_path, 'w') as file:
            json.dump(profit_history, file, indent=4)

        print(f'Order for {orders[coin][0]["symbol"]} with ID {orders[coin][0]["orderId"]} placed and saved to file.')


def remove_from_portfolio(coins_sold):
    '''Remove coins sold due to SL or TP from portfolio'''
    for coin,data in coins_sold.items():
        symbol = coin
        order_id = data['orderid']
        # code below created by getsec <3
        for bought_coin, bought_coin_data in coins_bought.items():
            if bought_coin_data['orderid'] == order_id:
                print(f"Sold {bought_coin}, removed order ID {order_id} from history.")
                coins_bought.pop(bought_coin)
                with open(coins_bought_file_path, 'w') as file:
                    json.dump(coins_bought, file, indent=4)
                break




#         coins_bought_new = list(filter(lambda ID : (coin['orderid'] != ID) , coins_bought))



#         if coins_bought[coin]['orderid'] == ID:
#             print(f"found {coin} with orderid {coins_sold[coin]['orderid']}")
#             coins_bought.pop(coin)
#             print(f"removed {ID}")

#         with open(coins_bought_file_path, 'w') as file:
#             json.dump(coins_bought_new, file, indent=4)


def write_log(logline):
    timestamp = datetime.now().strftime("%d/%m %H:%M:%S")
    with open(LOG_FILE,'a+') as f:
        f.write(timestamp + ' ' + logline + '\n')

def unrealised_percent_calc():
    global unrealised_percent_delay, unrealised_percent
    if (unrealised_percent_delay > 3):
        unrealised_percent = 0
        for coin in list(coins_bought):
            LastPrice = float(last_price[coin]['price'])
            # sell fee below would ofc only apply if transaction was closed at the current LastPrice
            sellFee = (LastPrice * (TRADING_FEE/100))
            BuyPrice = float(coins_bought[coin]['bought_at'])
            buyFee = (BuyPrice * (TRADING_FEE/100))
            PriceChange = float((LastPrice - BuyPrice) / BuyPrice * 100)
            if len(coins_bought) > 0:
                unrealised_percent = unrealised_percent + (PriceChange-(buyFee+sellFee))
                unrealised_percent_delay = 0
    else:
        unrealised_percent_delay =  unrealised_percent_delay + 1
    return unrealised_percent

if __name__ == '__main__':

    # Load arguments then parse settings
    args = parse_args()
    mymodule = {}

    # set to false at Start
    global bot_paused
    bot_paused = False

    DEFAULT_CONFIG_FILE = 'config.yml'
    DEFAULT_CREDS_FILE = 'creds.yml'

    config_file = args.config if args.config else DEFAULT_CONFIG_FILE
    creds_file = args.creds if args.creds else DEFAULT_CREDS_FILE
    parsed_config = load_config(config_file)
    parsed_creds = load_config(creds_file)

    # Default no debugging
    DEBUG = False

    # Load system vars
    TEST_MODE = parsed_config['script_options']['TEST_MODE']
#     LOG_TRADES = parsed_config['script_options'].get('LOG_TRADES')
    LOG_FILE = parsed_config['script_options'].get('LOG_FILE')
    DEBUG_SETTING = parsed_config['script_options'].get('DEBUG')
    AMERICAN_USER = parsed_config['script_options'].get('AMERICAN_USER')

    # Load trading vars
    PAIR_WITH = parsed_config['trading_options']['PAIR_WITH']
    QUANTITY = parsed_config['trading_options']['QUANTITY']
    TRADE_SLOTS = parsed_config['trading_options']['TRADE_SLOTS']
    FIATS = parsed_config['trading_options']['FIATS']
    TIME_DIFFERENCE = parsed_config['trading_options']['TIME_DIFFERENCE']
    RECHECK_INTERVAL = parsed_config['trading_options']['RECHECK_INTERVAL']
    CHANGE_IN_PRICE = parsed_config['trading_options']['CHANGE_IN_PRICE']
    STOP_LOSS = parsed_config['trading_options']['STOP_LOSS']
    TAKE_PROFIT = parsed_config['trading_options']['TAKE_PROFIT']
    CUSTOM_LIST = parsed_config['trading_options']['CUSTOM_LIST']
    TICKERS_LIST = parsed_config['trading_options']['TICKERS_LIST']
    USE_TRAILING_STOP_LOSS = parsed_config['trading_options']['USE_TRAILING_STOP_LOSS']
    TRAILING_STOP_LOSS = parsed_config['trading_options']['TRAILING_STOP_LOSS']
    TRAILING_TAKE_PROFIT = parsed_config['trading_options']['TRAILING_TAKE_PROFIT']
    TRADING_FEE = parsed_config['trading_options']['TRADING_FEE']
    SIGNALLING_MODULES = parsed_config['trading_options']['SIGNALLING_MODULES']
    if DEBUG_SETTING or args.debug:
        DEBUG = True

    # Load creds for correct environment
    access_key, secret_key = load_correct_creds(parsed_creds)

    if DEBUG:
        print(f'Loaded config below\n{json.dumps(parsed_config, indent=4)}')
        print(f'Your credentials have been loaded from {creds_file}')


    # Authenticate with the client, Ensure API key is good before continuing
    if AMERICAN_USER:
        client = Client(access_key, secret_key, tld='us')
    else:
        client = Client(access_key, secret_key)

    # If the users has a bad / incorrect API key.
    # this will stop the script from starting, and display a helpful error.
    api_ready, msg = test_api_key(client, BinanceAPIException)
    if api_ready is not True:
       exit(f'{txcolors.SELL_LOSS}{msg}{txcolors.DEFAULT}')

    # Use CUSTOM_LIST symbols if CUSTOM_LIST is set to True
    if CUSTOM_LIST: tickers=[line.strip() for line in open(TICKERS_LIST)]

    # try to load all the coins bought by the bot if the file exists and is not empty
    coins_bought = {}

    # path to the saved coins_bought file
    coins_bought_file_path = 'coins_bought.json'

    # The below mod was stolen and altered from GoGo's fork, a nice addition for keeping a historical history of profit across multiple bot sessions.
    # profit_history is calculated in %, apparently: "this is inaccurate if QUANTITY is not the same!"
    profit_history_file_path = 'profit_history.json'

    if os.path.isfile(profit_history_file_path) and os.stat(profit_history_file_path).st_size!= 0:
       json_file=open(profit_history_file_path)
       profit_history=json.load(json_file)
       json_file.close()

    # rolling window of prices; cyclical queue
    historical_prices = [None] * (TIME_DIFFERENCE * RECHECK_INTERVAL)
    hsp_head = -1

    # prevent including a coin in volatile_coins if it has already appeared there less than TIME_DIFFERENCE minutes ago
    volatility_cooloff = {}

    # use separate files for testing and live trading
    if TEST_MODE:
        coins_bought_file_path = 'test_' + coins_bought_file_path

    # if saved coins_bought json file exists and it's not empty then load it
    if os.path.isfile(coins_bought_file_path) and os.stat(coins_bought_file_path).st_size!= 0:
        with open(coins_bought_file_path) as file:
                coins_bought = json.load(file)

    print('Press Ctrl-Q to stop the script')

    if not TEST_MODE:
        if not args.notimeout: # if notimeout skip this (fast for dev tests)
            print('WARNING: test mode is disabled in the configuration, you are using live funds.')
            print('WARNING: Waiting 10 seconds before live trading as a security measure!')
            time.sleep(10)

    signals = glob.glob("signals/*.exs")
    for filename in signals:
        for line in open(filename):
            try:
                os.remove(filename)
            except:
                if DEBUG: print(f'{txcolors.WARNING}Could not remove external signalling file {filename}{txcolors.DEFAULT}')

    if os.path.isfile("signals/paused.exc"):
        try:
            os.remove("signals/paused.exc")
        except:
            if DEBUG: print(f'{txcolors.WARNING}Could not remove external signalling file {filename}{txcolors.DEFAULT}')

    # load signalling modules
    try:
        if len(SIGNALLING_MODULES) > 0:
            for module in SIGNALLING_MODULES:
                print(f'Starting {module}')
                mymodule[module] = importlib.import_module(module)
                t = threading.Thread(target=mymodule[module].do_work, args=())
                t.daemon = True
                t.start()
                time.sleep(2)
        else:
            print(f'No modules to load {SIGNALLING_MODULES}')
    except Exception as e:
        print(e)

    # seed initial prices
    get_price()
    while True:
        orders, last_price, volume = buy()
        update_portfolio(orders, last_price, volume)
        coins_sold = sell_coins()
        remove_from_portfolio(coins_sold)