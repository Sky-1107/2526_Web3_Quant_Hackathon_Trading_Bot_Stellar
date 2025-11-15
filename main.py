import hmac, requests, time
import pandas as pd
from dotenv import load_dotenv
from hashlib import sha256
from os import environ
from requests.exceptions import RequestException

load_dotenv()
API_KEY, API_SECRET, X_API_KEY = environ["API_KEY"], environ["API_SECRET"], environ["X_API_KEY"]
BASE_URL = "https://mock-api.roostoo.com"

# ------------------------------
# Utility Functions
# ------------------------------

def _get_timestamp():
    """Return a 13-digit millisecond timestamp as string."""
    return str(int(time.time() * 1000))

def _get_signed_headers(payload: dict = {}):
    """
    Generate signed headers and totalParams for `RCL_TopLevelCheck` endpoints.
    """
    payload['timestamp'] = _get_timestamp()
    total_params = "&".join(f"{k}={payload[k]}" for k in sorted(payload.keys()))
    signature = hmac.new(API_SECRET.encode('utf-8'), total_params.encode('utf-8'), sha256).hexdigest()
    headers = {
        'RST-API-KEY': API_KEY,
        'MSG-SIGNATURE': signature
    }
    return headers, payload, total_params

def _get_request(url: str = "", error_prompt: str = "", headers: dict = None, params: dict = None):
    """Attempts to send a `GET` request."""
    try:
        if headers == None:
            r = requests.get(url, params = params)
        else:
            r = requests.get(url, headers = headers, params = params)
        r.raise_for_status()
        return r.json()
    except RequestException as e:
        print(f"Error {error_prompt}: {e}")
        print(f"Response text: {e.response.text if e.response else 'N/A'}")
        return None

def _post_request(url: str = "", error_prompt: str = "", payload: dict = {}):
    """Attempts to send a `POST` request."""
    headers, _, total_params = _get_signed_headers(payload)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        r = requests.post(url, headers = headers, data = total_params)
        r.raise_for_status()
        return r.json()
    except RequestException as e:
        print(f"Error {error_prompt}: {e}")
        print(f"Response text: {e.response.text if e.response else 'N/A'}")
        return None

# ------------------------------
# Roostoo Public API - Public Endpoints
# ------------------------------

def check_server_time():
    """Check API server time."""
    return _get_request(f"{BASE_URL}/v3/serverTime", "checking server time")

def get_exchange_info():
    """Get exchange trading pairs and info."""
    return _get_request(f"{BASE_URL}/v3/exchangeInfo", "getting exchange info")

def get_coin_precision(coin: str, exchange_info: dict) -> int:
    """Get the precision for a specific coin."""

    if not exchange_info or "TradePairs" not in exchange_info:
        return None
    for info in exchange_info['TradePairs'].values():
        if info['Coin'] == coin:
            return info['AmountPrecision']
    print(f"Error obtaining precision for {coin}.")
    return None

def get_price_precision(coin: str, exchange_info: dict) -> int:
    """Get the precision for a specific coin."""

    if not exchange_info or "TradePairs" not in exchange_info:
        return None
    for info in exchange_info['TradePairs'].values():
        if info['Coin'] == coin:
            return info['PricePrecision']
    print(f"Error obtaining precision for {coin}.")
    return None

def get_ticker(pair = None):
    """Get ticker for one or all pairs."""
    params = {'timestamp': _get_timestamp()}
    if pair:
        params['pair'] = pair
    return _get_request(f"{BASE_URL}/v3/ticker", "getting ticker", params = params)

# ------------------------------
# Roostoo Public API - Signed Endpoints
# ------------------------------

def get_balance():
    """Get wallet balances (RCL_TopLevelCheck)."""
    headers, payload, _ = _get_signed_headers()
    return _get_request(f"{BASE_URL}/v3/balance", "getting balance", headers = headers, params = payload)

def get_pending_count():
    """Get total pending order count."""
    headers, payload, _ = _get_signed_headers()
    return _get_request(f"{BASE_URL}/v3/pending_count", "getting pending count", headers = headers, params = payload)

def place_order(pair_or_coin: str, side: str, quantity: int, price: float = None, order_type: str = None):
    """Place a `LIMIT` or `MARKET` order."""
    if order_type is None:
        order_type = "LIMIT" if price is not None else "MARKET"
    if order_type == 'LIMIT' and price is None:
        print("Error: LIMIT orders require 'price'.")
        return None
    payload = {
        'pair': f"{pair_or_coin}/USD" if "/" not in pair_or_coin else pair_or_coin,
        'side': side.upper(),
        'type': order_type.upper(),
        'quantity': str(quantity)
    }
    if order_type == 'LIMIT':
        payload['price'] = str(price)
    return _post_request(f"{BASE_URL}/v3/place_order", "placing order", payload)

def query_order(order_id = None, pair: str = None, pending_only: bool = None):
    """Query order history or pending orders."""
    payload = {}
    if order_id:
        payload['order_id'] = str(order_id)
    elif pair:
        payload['pair'] = pair
        if pending_only is not None:
            payload['pending_only'] = 'TRUE' if pending_only else 'FALSE'
    return _post_request(f"{BASE_URL}/v3/query_order", "querying order", payload)

def cancel_order(order_id = None, pair: str = None):
    """Cancel specific or all pending orders."""
    payload = {}
    if order_id:
        payload['order_id'] = str(order_id)
    elif pair:
        payload['pair'] = pair
    return _post_request(f"{BASE_URL}/v3/cancel_order", "cancelling order", payload)

# ------------------------------
# Horus API
# ------------------------------

def get_total_asset(balance_data: dict):
    spot_wallet: dict = balance_data.get('SpotWallet', {})
    total_usd = spot_wallet.get('USD', {}).get('Free', 0) + spot_wallet.get('USD', {}).get('Lock', 0)
    for coin, balance_info in spot_wallet.items():
        if coin != 'USD' and coin != 'USDT':
            total_amount = balance_info.get('Free', 0) + balance_info.get('Lock', 0)
            if total_amount > 0:
                ticker = get_ticker(f"{coin}/USD")
                if ticker and ticker.get('Success'):
                    total_usd += total_amount * ticker['Data'][f"{coin}/USD"]['LastPrice']
                else:
                    print(f"Error obtaining the current price of {coin}.")
    print(f"Total USD: {total_usd}")
    return total_usd

def get_ohlcv(asset: str = "BTC", interval: str = "15m", days: int = 90):
    """
    Get historical OHLCV data from Horus API.

    Parameters:
        asset (str, default "BTC") : Cryptocurrency.

        interval (str, default "1h") : Data interval. Options: `"15m", "1h", "1d"`.
    
        days (int, default 180) : Number of days of historical data to be retrieved.
    """

    current_time = int(time.time())
    try:
        # Construct a `DataFrame` from the returned data
        df = pd.DataFrame(
            _get_request(
                "https://api-horus.com/market/price",
                "sending request to Horus API",
                headers = {"X-Api-Key": X_API_KEY},
                params = {
                    "asset": asset.replace("/USD", ""),  # e.g. "BTC"
                    "interval": interval,
                    "start": current_time - 86400 * days,
                    "end": current_time
                }
            )
        )
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit = 's')
        df = df.rename(columns = {'price': 'close'})
        
        # Construct OHLCV columns
        df['open'] = df['close'].shift(1)           # Set the open price as previous close price
        df['high'] = df['close'].rolling(5).max()   # 5-period high
        df['low'] = df['close'].rolling(5).min()    # 5-period low
        df['volume'] = 0                            # Placeholder for volume (not provided by Horus)
        
        return df.sort_values('timestamp').reset_index(drop = True)
    except Exception as e:
        print(f"Error obtaining OHLCV data: {e}")
        return None

def calculate_atr(df: pd.DataFrame, period: int = 20):
    high_low = df['high'] - df['low']
    high_close_prev = abs(df['high'] - df['close'].shift(1))
    low_close_prev = abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis = 1).max(axis = 1)
    atr = tr.rolling(window = period).mean()
    return atr

def calculate_technical_indicators(df: pd.DataFrame, short_period: int = 7, long_period: int = 40, atr_period: int = 80):
    df['short_MA'] = df['close'].ewm(span = short_period).mean()
    df['long_MA'] = df['close'].rolling(window = long_period).mean()
    df['stdV'] = df['close'].rolling(window = short_period).std()
    df['std_volavolatility_ratio'] = df['close'].rolling(window = 1000).std() / df['close'].rolling(window = 1000).mean()
    df['atr'] = calculate_atr(df, atr_period)
    return df

def calculate_max_position(df: pd.DataFrame, total_capital: float, risk_coefficient: float = 0.05):
    current_price = df['close'].iloc[-1]
    current_std = df['stdV'].iloc[-1]
    std_volavolatility_ratio = df['std_volavolatility_ratio'].iloc[-1]
    if current_std == 0:
        current_std = current_price * 0.001
    volatility_ratio = current_std / current_price
    max_position = total_capital * risk_coefficient / (volatility_ratio / std_volavolatility_ratio)
    print(f"volatility_ratio: {volatility_ratio}")
    return max_position

def calculate_coefficient(df):
    latest = df.iloc[-1]
    if pd.isna(latest['atr']) or latest['atr'] == 0:
        return 0
    ma_diff = latest['short_MA'] - latest['long_MA']
    current_price = df['close'].iloc[-1]
    current_std = df['stdV'].iloc[-1]
    if current_std == 0:
        current_std = current_price * 0.01
    std_volavolatility_ratio = latest['std_volavolatility_ratio']
    objective_volatility_ratio = 0.02 / std_volavolatility_ratio
    objective_volatility_ratio = max(0.9, min(1.11, objective_volatility_ratio))
    coefficient = objective_volatility_ratio * ma_diff / latest['atr']
    return coefficient

class Trading_Bot:
    def run(self, safety: int = 1000, safety_coefficient: float = 0.4):
        coin_list = [
            'BTC', 'ETH', 'BNB', 'XRP', 'DOGE', 'ADA', 'SOL', 'TRX', 'LTC', 'DOT',
            'AVAX', 'SHIB', 'LINK', 'UNI', 'AAVE', 'ICP', 'NEAR', 'ARB', 'TON', 'FIL'
        ]
        sellpoint = 0
        while True:
            print(get_balance())
            balance = get_balance()
            decision_list = []
            exchange_info = get_exchange_info()
            print("balance: ",balance)
            for coin in coin_list:
                print(f"-- Trading {coin} ---")
                decision = self.strategy(coin, balance, sellpoint, safety, safety_coefficient)
                decision['coin'] = coin
                decision_list.append(decision)
                time.sleep(2)
            decision_list.sort(key = lambda x: -(x.get('coefficient')))
            sellpoint = max(0.5, decision_list[2].get('coefficient', 0) * 0.95)
            decision_list.sort(key = lambda x: (x.get('action') == "NULL", x.get('action') == 'BUY', -abs(x.get('coefficient'))))
            print(f'======= NEW TRADE WITH THRESHOLD {sellpoint} =======')
            for decision in decision_list:
                print(decision)
                coin = decision['target']
                if decision['action'] == 'BUY' and (balance.get('SpotWallet',{}).get('USD',{}).get('Free',0) > safety) and decision['balance_USD']<decision['Max_position']:
                    print('-----------------------------------')
                    amount=round(decision['amount'], get_coin_precision(coin, exchange_info))
                    print(place_order(coin, "BUY", amount))
                    print("*****")
                    time.sleep(5)
                    print(place_order(coin, "SELL", amount, price=round(decision['sell_price'], get_price_precision(coin, exchange_info))))
                    print('-----------------------------------')
                    time.sleep(5)
                elif decision['action'] == 'SELL':
                    print('-----------------------------------')
                    print(cancel_order(pair=f"{coin}/USD"))
                    print(place_order(coin, "SELL", round(decision['amount'], get_coin_precision(coin, exchange_info))))
                    print('-----------------------------------')
                    time.sleep(5)
            time.sleep(20)
    
    def strategy(self, target, balance, threshold, safety = 1000, safety_coefficient = 0.4):
        try:
            ticker = get_ticker(f"{target}/USD")
            if ticker and ticker.get('Success'):
                price = ticker['Data'][f"{target}/USD"]['LastPrice']
            data = get_ohlcv(f"{target}/USD")
            data = calculate_technical_indicators(data)
            max_position = calculate_max_position(data, get_total_asset(balance))

            print(data.tail(1))

            coefficient = calculate_coefficient(data)

            decision={
                'target': target,
                'action':'NULL',
                'amount': abs(max_position*coefficient)/price,
                'coefficient': coefficient,
                'Max_position': max_position,
                'balance':balance.get('SpotWallet',{}).get(target,{}).get('Free',0)+balance.get('SpotWallet',{}).get(target,{}).get('Lock',0),
                'price':price
            }
            current_USD = balance.get('SpotWallet',{}).get('USD',{}).get('Free',0)
            decision['balance_USD']=decision['balance']*price
            decision['coefficient'] = min(5, decision['coefficient'])
            if coefficient > threshold + 0.1:
                decision['action'] = 'BUY'
                decision['amount'] = min(
                    current_USD * safety_coefficient / price,
                    abs(max_position * coefficient) / price
                )
                decision['spending'] = decision['amount']*price
            #print('sell price: ', (data['stdV'].values[-1]))
            decision['sell_price'] = price + 3 * (data['stdV'].values[-1])
                # To suppress large purchases
                #decision['amount'] = decision['amount'] ** (1 - (decision['spending'] / current_USD) ** 3)
                #decision['spending'] = decision['amount']*price
            if coefficient < threshold:
                decision['action'] ='SELL'
                #decision['amount'] = min(decision.get('balance', 0),abs(max_position * coefficient) / price)
                decision['amount'] = decision.get('balance', 0)
            if decision['amount'] == 0:
                decision['action'] ='NULL'
            decision['spending'] = decision['amount'] * price
            return decision
        except Exception as e:
            print(e)
            time.sleep(5)
            decision={
                'target': target,
                'action':'NULL',
                'amount': 0,
                'coefficient': 0,
                'Max_position': 0
            }
            return decision

if __name__ == "__main__":
    bot = Trading_Bot()
    while True:
        print('-------======****)] Bot Deployed [(****======-------')
        try:
            bot.run()
        except Exception as e:
            print(e)
            time.sleep(10)
