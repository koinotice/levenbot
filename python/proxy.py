import ccxt
exchange = ccxt.binance()

exchange.session.verify= False        # Do not reject on SSL certificate checks
exchange.session.trust_env=False   # Ignore any Environment HTTP/S Proxy and No_Proxy variables
exchange.load_markets()