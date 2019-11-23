# coding=utf-8

import hashlib
import hmac
import requests
import time
import websocket
import ujson
import asyncio
from operator import itemgetter
from .helpers import date_to_milliseconds, interval_to_milliseconds
from .exceptions import LoopringAPIException, LoopringRequestException, LoopringWithdrawException

# for order sign
from ethsnarks.eddsa import PureEdDSA
from ethsnarks.field import FQ

class Client(object):

    API_URL = 'http://13.112.139.43:31610/api'
    STREAM_URL = "ws://13.112.139.43:31610/v1/ws"
    WITHDRAW_API_URL = API_URL
    WEBSITE_URL = 'http://3.115.185.64:8080'
    PUBLIC_API_VERSION = 'v1'
    PRIVATE_API_VERSION = 'v1'
    WITHDRAW_API_VERSION = 'v1'

    CONNCECTION_TIMEOUT = 10

    SYMBOL_TYPE_SPOT = 'SPOT'

    SIDE_BUY = 'BUY'
    SIDE_SELL = 'SELL'

    ORDER_TYPE_LIMIT = 'LIMIT'
    ORDER_TYPE_MARKET = 'MARKET'

    TIME_IN_FORCE_GTC = 'GTC'  # Good till cancelled
    TIME_IN_FORCE_IOC = 'IOC'  # Immediate or cancel
    TIME_IN_FORCE_FOK = 'FOK'  # Fill or kill

    ORDER_RESP_TYPE_ACK = 'ACK'
    ORDER_RESP_TYPE_RESULT = 'RESULT'
    ORDER_RESP_TYPE_FULL = 'FULL'

    def __init__(self, api_key, api_secret, exchangeId, accountId, maxFeeBips, pubKeyX, pubKeyY, secretKey, requests_params=None):
        """Loopring API Client constructor
        """
        self.API_KEY = api_key
        self.API_SECRET = api_secret
        self.session = self._init_session()
        self._requests_params = requests_params

        """
        {
            "secKey": ""
            "apiKey": ""
            "exchangeId": 1,
            "orderId": 1,
            "accountId": 6,
            "maxFeeBips": 20,
            "tradingPubKeyX": "",
            "tradingPubKeyY": "",
            "dualAuthPubKeyX": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "dualAuthPubKeyY": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "dualAuthPrivKey": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            }
        """
        
        self.exchangeId = exchangeId
        self.accountId = 12
        self.maxFeeBips = maxFeeBips
        self.tradingPubKeyX = pubKeyX
        self.tradingPubKeyY = pubKeyY
        self.dualAuthPubKeyX = "20427978695829389921027882814288154063458566858893427861603715087273059264885"
        self.dualAuthPubKeyY = "20427978695829389921027882814288154063458566858893427861603715087273059264885"
        self.dualAuthPrivKey = "20427978695829389921027882814288154063458566858893427861603715087273059264885"
        self.secretKey = secretKey
        self.initSymbolIdTable()
        # init DNS and SSL cert
        self.ping()

    def _init_session(self):
        session = requests.session()
        session.headers.update({'Accept': 'application/json',
                                'X-MBX-APIKEY': self.API_KEY})
        return session

    def _create_api_uri(self, path, signed=True, version=PUBLIC_API_VERSION):
        v = self.PRIVATE_API_VERSION if signed else version
        return self.API_URL + '/' + v + '/' + path

    def _create_withdraw_api_uri(self, path):
        return self.WITHDRAW_API_URL + '/' + self.WITHDRAW_API_VERSION + '/' + path

    def _create_website_uri(self, path):
        return self.WEBSITE_URL + '/' + path

    def _generate_signature(self, data):

        ordered_data = self._order_params(data)
        query_string = '&'.join(["{}={}".format(d[0], d[1]) for d in ordered_data])
        m = hmac.new(self.API_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256)
        return m.hexdigest()

    def _order_params(self, data):
        """Convert params to list with signature as last element

        :param data:
        :return:

        """
        has_signature = False
        params = []
        for key, value in data.items():
            if key == 'signature':
                has_signature = True
            else:
                params.append((key, value))
        # sort parameters by key
        params.sort(key=itemgetter(0))
        if has_signature:
            params.append(('signature', data['signature']))
        return params

    def _request(self, method, uri, signed, force_params=False, **kwargs):

        # set default requests timeout
        kwargs['timeout'] = 10

        # add our global requests params
        if self._requests_params:
            kwargs.update(self._requests_params)

        data = kwargs.get('data', None)
        if data and isinstance(data, dict):
            kwargs['data'] = data

            # find any requests params passed and apply them
            if 'requests_params' in kwargs['data']:
                # merge requests params into kwargs
                kwargs.update(kwargs['data']['requests_params'])
                del(kwargs['data']['requests_params'])

        if signed:
            # generate signature
            kwargs['data']['timestamp'] = int(time.time() * 1000)
            kwargs['data']['signature'] = self._generate_signature(kwargs['data'])

        # sort get and post params to match signature order
        if data:
            # sort post params
            kwargs['data'] = self._order_params(kwargs['data'])

        # if get request assign data array to params value for requests lib
        if data and (method == 'get' or force_params):
            kwargs['params'] = kwargs['data']
            del(kwargs['data'])

        response = getattr(self.session, method)(uri, **kwargs)
        # print(response.text)
        return self._handle_response(uri, response)

    def _request_api(self, method, path, signed=False, version=PUBLIC_API_VERSION, **kwargs):
        uri = self._create_api_uri(path, signed, version)
        # print("DEBUG: "+uri)
        return self._request(method, uri, signed, **kwargs)

    def _request_withdraw_api(self, method, path, signed=False, **kwargs):
        uri = self._create_withdraw_api_uri(path)

        return self._request(method, uri, signed, True, **kwargs)

    def _request_website(self, method, path, signed=False, **kwargs):

        uri = self._create_website_uri(path)

        return self._request(method, uri, signed, **kwargs)

    def _handle_response(self, reqUri, response):
        """Internal helper for handling API responses from the Loopring server.
        Raises the appropriate exceptions when necessary; otherwise, returns the
        response.
        """
        # print(f'response.text={response.text}')
        # print(response)
        if not str(response.status_code).startswith('2'):
            raise LoopringRequestException('Req %s gets invalid Response: %s' % (reqUri, response.text))
        try:
            return response.json()
        except ValueError:
            raise LoopringRequestException('Req %s gets invalid Response: %s' % (reqUri, response.text))

    def _get(self, path, signed=False, version=PUBLIC_API_VERSION, **kwargs):
        return self._request_api('get', path, signed, version, **kwargs)

    def _post(self, path, signed=False, version=PUBLIC_API_VERSION, **kwargs):
        return self._request_api('post', path, signed, version, **kwargs)

    def _put(self, path, signed=False, version=PUBLIC_API_VERSION, **kwargs):
        return self._request_api('put', path, signed, version, **kwargs)

    def _delete(self, path, signed=False, version=PUBLIC_API_VERSION, **kwargs):
        return self._request_api('delete', path, signed, version, **kwargs)

    # Exchange Endpoints
    def initSymbolIdTable(self):
        raw_data = self._get('tokenInfo', data={'symbols':'*'})
        self.tokenIdMap = {item['symbol']:item['tokenId'] for item in raw_data['tokens'] }
        self.tokenNameMap = {item['tokenId']:item['symbol'] for item in raw_data['tokens'] }
        self.tokenDecimalsMap = {item['tokenId']:item['decimals'] for item in raw_data['tokens'] }
        self.tokenOrderIdMap = {}
        for item in raw_data['tokens']:
            # symbol = item['symbol']
            tokenId = item['tokenId']
            print(self.accountId)
            resp = self._get('orderId', data={'accountId':self.accountId, 'tokenSId':tokenId})
            print(resp)
            self.tokenOrderIdMap[tokenId] = resp['orderId']

        # print(self.tokenIdMap)
        # print(self.tokenNameMap)
        # print(self.tokenDecimalsMap)
        print (self.tokenOrderIdMap)

    def get_products(self):
        raise NotImplementedError
        products = self._request_website('get', 'exchange/public/product')
        return products

    def get_exchange_info(self):
        # raise NotImplementedError
        """
        {
            "markets": [
                {
                "market": "string",
                "baseToken": "string",
                "quoteToken": "string",
                "pricePrecision": 0,
                "amountPrecision": 0,
                "totalPrecision": 0,
                "maxLevel": 0
                }
            ]
        }
        """
        return self._get('marketInfo', data={'symbol':'*'})

    def get_symbol_info(self, symbol):
        # raise NotImplementedError
        res = self._get('tokenInfo', data={'symbol':'*'})
        for item in res['tokens']:
            if item['symbol'] == symbol.upper():
                return item
        return None

    # General Endpoints

    def ping(self):
        """Test connectivity to the Rest API.
        :raises: LoopringRequestException, LoopringAPIException
        """
        return self._get('timestamp')

    def get_server_time(self):
        """
        {
            "timestamp": 0
        }
        """
        return self._get('timestamp')

    # Market Data Endpoints

    def get_all_tickers(self):
        raise NotImplementedError
        return self._get('ticker/allPrices')

    def get_orderbook_tickers(self):
        raise NotImplementedError
        return self._get('ticker/allBookTickers')

    def get_order_book(self, **params):
        """Get the Order Book for the market
        .. input:
            {
                "market": "LRC-BTC",
                "level": 8,
                "limit": 50
            }

        :returns: API response

        .. code-block:: python
            {
                "depth": {
                    "version": 0,
                    "timestamp": 0,
                    "bids": [
                    {
                        "price": "string",
                        "size": "string",
                        "volume": "string",
                        "count": 0
                    }
                    ],
                    "asks": [
                    {
                        "price": "string",
                        "size": "string",
                        "volume": "string",
                        "count": 0
                    }
                    ]
                }
            }
        """
        return self._get('depth', data=params)

    def get_recent_trades(self, **params):
        """Get recent trades (up to last 500).
            {
                "market": "LRC-BTC",
                "fromId": 1,
                "limit": 50
            }

        :returns: API response

        .. code-block:: python
            {
                "trades": [
                    {
                    "timestamp": 0,
                    "tradeId": 0,
                    "side": "string",
                    "size": "string",
                    "price": "string",
                    "fee": "string"
                    }
                ]
            }

        """
        return self._get('trade', data=params)

    # def get_next_orderId(self, tokenId):
    #     """
    #     {
    #         "orderId": 0
    #     }
    #     """
    #     resp = self._get('orderId', data={'accountId':self.accountId, 'tokenId':tokenId})
    #     return resp['orderId']

    def get_historical_trades(self, **params):
        raise NotImplementedError
        return self._get('historicalTrades', data=params)

    def get_aggregate_trades(self, **params):
        raise NotImplementedError

    def aggregate_trade_iter(self, symbol, start_str=None, last_id=None):
        raise NotImplementedError

    def get_klines(self, **params):
        """Kline/candlestick works in data stream.
        {
            "op": "sub",
            "args": [
                "kline&LRC-BTC&1Hour",
            ]
        }
        {
            "topic": "kline&lrc-btc&1hour",
            "ts":1565844208,
            "data": {
                "openTime": 1565844208,
                "count":5000,
                "size": "500000000000000000",
                "volume": "2617521141385000000",
                "open": "3997.3",
                "close": "3998.7",
                "high": "4031.9",
                "low": "3982.5"
            }
        }
        :raises: LoopringRequestException, LoopringAPIException

        """
        raise NotImplementedError

    def get_ticker(self, **params):
        raise NotImplementedError

    def get_symbol_ticker(self, **params):
        raise NotImplementedError

    def get_orderbook_ticker(self, **params):
        raise NotImplementedError

    # Account Endpoints
    def create_order(self, **params):
        """
        {
            "exchangeId": 1,
            "orderId": 1,
            "accountId": 1,
            "tokenSId": 1,
            "tokenBId": 1,
            "amountS": "1000000000000000000",
            "amountB": "1000000000000000000",
            "hash": "15280744035821602051101821301291351528331454145019142062173341016567400924288",
            "maxFeeBips": 20,
            "validSince": 1567053142,
            "validUntil": 1567053142,
            "tradingPubKeyX": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "tradingPubKeyY": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "dualAuthPubKeyX": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "dualAuthPubKeyY": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "dualAuthPrivKey": "20427978695829389921027882814288154063458566858893427861603715087273059264885",
            "tradingSigRx": "13375450901292179417154974849571793069911517354720397125027633242680470075859",
            "tradingSigRy": "13375450901292179417154974849571793069911517354720397125027633242680470075859",
            "tradingSigS": "13375450901292179417154974849571793069911517354720397125027633242680470075859",
            "clientOrderId": "1"
        }
        return
        {
            "orderHash": "string"
        }    
        """
        validSince = int(time.time())
        validUntil = validSince + 24 * 60 * 60 * 30
        maxFeeBips = self.maxFeeBips

        allOrNone = params['allOrNone']
        buy = params['buy']

        #sell baseToken i.e. LRC out and buy quoteToken i.e. ETH in.
        if buy == 0:
            tokenSId = self.tokenIdMap[params["baseToken"]]
            tokenBId = self.tokenIdMap[params["quoteToken"]]
            amountB = str(int(params["volume"] * 10**self.tokenDecimalsMap[tokenSId]))
            amountS = str(int(params["size"] * 10**self.tokenDecimalsMap[tokenSId]))
        else :
            tokenSId = self.tokenIdMap[params["quoteToken"]]
            tokenBId = self.tokenIdMap[params["baseToken"]]
            amountS = str(int(params["volume"] * 10**self.tokenDecimalsMap[tokenSId]))
            amountB = str(int(params["size"] * 10**self.tokenDecimalsMap[tokenSId]))

        orderId = self.tokenOrderIdMap[tokenSId]
        self.tokenOrderIdMap[tokenSId] = orderId+1
        clientOrderId = params["newClientOrderId"]
        msg_parts = [
            FQ(int(self.exchangeId), 1 << 32), FQ(int(orderId), 1 << 20),
            FQ(int(self.accountId), 1 << 20),
            FQ(int(self.tradingPubKeyX), 1 << 254), FQ(int(self.tradingPubKeyY), 1 << 254),
            FQ(int(tokenSId), 1 << 8), FQ(int(tokenBId), 1 << 8),
            FQ(int(amountS), 1 << 96), FQ(int(amountB), 1 << 96),
            FQ(int(allOrNone), 1 << 1), FQ(int(validSince), 1 << 32), FQ(int(validUntil), 1 << 32),
            FQ(int(maxFeeBips), 1 << 6),
            FQ(int(buy), 1 << 1)
        ]
        message = PureEdDSA.to_bits(*msg_parts)
        signedMessage = PureEdDSA.sign(message, FQ(int(self.secretKey)))
        hashMsg = PureEdDSA().hash_public(signedMessage.sig.R, signedMessage.A, signedMessage.msg)
        newOrder = {
            "exchangeId": self.exchangeId,
            "orderId": orderId,
            "accountId": self.accountId,
            "tokenSId": tokenSId,
            "tokenBId": tokenBId,
            "amountS": amountS,
            "amountB": amountB,
            "hash": str(hashMsg),
            "maxFeeBips": 20,
            "validSince": validSince,
            "validUntil": validUntil,
            "tradingPubKeyX": self.tradingPubKeyX,
            "tradingPubKeyY": self.tradingPubKeyY,
            "dualAuthPubKeyX": self.dualAuthPubKeyX,
            "dualAuthPubKeyY": self.dualAuthPubKeyY,
            "dualAuthPrivKey": self.dualAuthPrivKey,
            "tradingSigRx": str(signedMessage.sig.R.x),
            "tradingSigRy": str(signedMessage.sig.R.y),
            "tradingSigS":  str(signedMessage.sig.s),
            "clientOrderId": clientOrderId,
        }
        print(newOrder)
        # return
        return self._post('order', True, data=newOrder)

    def order_limit(self, timeInForce=TIME_IN_FORCE_GTC, **params):
        return self.create_order(**params)

    def order_limit_buy(self, timeInForce=TIME_IN_FORCE_GTC, **params):
        return self.order_limit(timeInForce=timeInForce, **params)

    def order_limit_sell(self, timeInForce=TIME_IN_FORCE_GTC, **params):
        return self.order_limit(timeInForce=timeInForce, **params)

    def order_market(self, **params):
        raise NotImplementedError
        params.update({
            'type': self.ORDER_TYPE_MARKET
        })
        return self.create_order(**params)

    def order_market_buy(self, **params):
        raise NotImplementedError
        params.update({
            'side': self.SIDE_BUY
        })
        return self.order_market(**params)

    def order_market_sell(self, **params):
        raise NotImplementedError
        params.update({
            'side': self.SIDE_SELL
        })
        return self.order_market(**params)

    def create_test_order(self, **params):
        raise NotImplementedError
        return self._post('order/test', True, data=params)

    def get_order(self, **params):
        """Check an order's status. Either orderId or origClientOrderId must be sent.
        {
            "accountId": 1,
            "orderHash": "2600105125336468966417510367500403435128941502452005674156103328855968837178"
        }
        {
            "hash": "string",
            "clientOrderId": "string",
            "size": "string",
            "volume": "string",
            "price": "string",
            "filledSize": "string",
            "filledVolume": "string",
            "filledFee": "string",
            "status": "string",
            "validSince": 0,
            "validUntil": 0,
            "timestamp": 0,
            "side": "string",
            "market": "string"
        }
        """
        return self._get('order', True, data={'orderHash':params['orderHash'], 'accountId':self.accountId})

    def get_all_orders(self, **params):
        raise NotImplementedError
        return self._get('allOrders', True, data=params)

    def cancel_order(self, **params):
        """Cancel an active order. Either orderId or origClientOrderId must be sent.
        {
            "accountId": 1,
            "orderHash": "2600105125336468966417510367500403435128941502452005674156103328855968837178",
            "clientOrderId": "1"
        }

        {
            "success": true
        }
        """
        # if params['orderHash'] == '':
        #     raise IOError("params['orderHash'] should be presented.")
        cancelParam = {
            "accountId": self.accountId,
            "orderHash": params['orderHash'],
            "clientOrderId": params['origClientOrderId']
        }
        # print(f"delete order {cancelParam}")
        return self._delete('orders', False, data=cancelParam)

    def get_open_orders(self, **params):
        raise NotImplementedError
        return self._get('openOrders', True, data=params)

    # User Stream Endpoints
    def get_account(self, **params):
        """Get current account information.

        {
            "accountId": 1,
            "tokenIds": 0
        }

        :returns: dictionary or None if not found

        {
        "balances": [
            {
            "accountId": 0,
            "tokenId": 0,
            "totalAmount": "string",
            "frozenAmount": "string"
            }
        ]
        }

        """

        accountInfo = {}
        # TODO: query specfic token id.
        # for tokenId in range(0, 128):
        reqParam = {
            "accountId": self.accountId,
            "tokenIds": 0
        }
        accountInfo = self._get('user/balances', True, data=reqParam)
        return accountInfo

    def get_asset_balance(self, asset, **params):
        """Get current asset balance.


        {
            "accountId": 1,
            "tokenIds": 1
        }

        :returns: dictionary or None if not found

        {
        "balances": [
            {
            "accountId": 0,
            "tokenId": 0,
            "totalAmount": "string",
            "frozenAmount": "string"
            }
        ]
        }

        """
        raise NotImplementedError
        res = self.get_account(**params)
        # find asset balance in list of balances
        if "balances" in res:
            for bal in res['balances']:
                if bal['asset'].lower() == asset.lower():
                    return bal
        return None

    def get_my_trades(self, **params):
        """
        {
            "accountId": 1,
            "market": "LRC-BTC",
            "statuses": "ORDER_STATUS_PROCESSING",
            "start": 1565844208,
            "end": 1565845208,
            "fromHash": "2600105125336468966417510367500403435128941502452005674156103328855968837178",
            "limit": 50
        }
        """
        request = {
            "accountId":self.accountId,
            "market": params['symbol'],
        }
        return self._get('orders', True, data=request)

    def get_system_status(self):
        raise NotImplementedError

    def get_account_status(self, **params):
        raise NotImplementedError

    def get_dust_log(self, **params):
        raise NotImplementedError

    def get_trade_fee(self, **params):
        """Get trade fee.
        {
            "resultInfo": {
                "code": 0,
                "message": "string"
        },
            "feeRates": [
                {
                    "symbol": "string",
                    "fee": "string",
                    "makerRebateFee": "string",
                    "takerRebateFee": "string"
                }
            ]
        }

        :raises: LoopringWithdrawException

        """
        res = self._get('feeRates', data=params)
        if res['resultInfo']['code'] != 0:
            raise LoopringWithdrawException(res['resultInfo']['message'])
        return res['feeRates']

    def get_asset_details(self, **params):
        raise NotImplementedError

    # Withdraw Endpoints
    def withdraw(self, **params):
        raise NotImplementedError

    def get_deposit_history(self, **params):
        raise NotImplementedError

    def get_withdraw_history(self, **params):
        raise NotImplementedError

    def get_deposit_address(self, **params):
        raise NotImplementedError

    def get_withdraw_fee(self, **params):
        raise NotImplementedError

    # User Stream Endpoints
    def stream_get_listen_key(self):
        raise NotImplementedError

    def stream_keepalive(self, listenKey):
        raise NotImplementedError

    def stream_open(self, url, **params):
        ws = websocket.create_connection(url)
        return ws

    def stream_close(self, listenKey):
        raise NotImplementedError

    def stream_subscribe(self, **params):
        """
        {
            "op": "sub",
            "args": [
                "kline&LRC-BTC&1Hour",
                "depth&LRC-BTC&1",
                "depth10&LRC-BTC&1",
                "trade&LRC-BTC",
                "ticker&LRC-BTC"
            ]
        }
        """
        # self.ws = self.stream_open(self.STREAM_URL, **params)
        ws = websocket.create_connection(self.STREAM_URL)
        ws_sub_op = {"op": "sub", "args": params['args']}
        # resp = ws.recv()
        subOpStr = ujson.dumps(ws_sub_op)
        ws.send(subOpStr)
        response = ws.recv()
        response = ujson.loads(response)
        if response['result']['status'] != 'ok':
            err = response['result']['error']
            raise IOError(f"Error websocket.send({subOpStr}) : {err}. ")
        self.ws = ws
        async def cbSocketRead():
            #TODO: use websockets
            async def wsRecv(ws: websocket.WebSocket) -> str:
                return ws.recv()
            
            while True:
                try:
                    msg: str = await asyncio.wait_for(wsRecv(ws), timeout=self.CONNCECTION_TIMEOUT)
                    if msg == 'ping':
                        ws.send('pong')
                    else:
                        #TODO: what if too many messages, i.e. not able to process on time.
                        yield msg
                except asyncio.CancelledError:
                    self.ws.close()
                    self.ws = None
                except:
                    await asyncio.sleep(3)
        return cbSocketRead

    def stream_unsubscribe(self, **params):
        if self.ws is not None:
            #org params
            unSubQp = ''
            try:
                ws.send(unSubQp)
            except:
                raise
            
        

