# coding=utf-8


class LoopringAPIException(Exception):

    def __init__(self, response):
        # self.code = 0
        # try:
        #     json_res = response.json()
        # except ValueError:
        #     self.message = 'Invalid JSON error message from Loopring: {}'.format(response.text)
        # else:
        #     self.code = json_res['code']
        #     self.message = json_res['msg']
        self.status_code = response.status_code
        self.response = response
        self.request = getattr(response, 'request', None)

    def __str__(self):  # pragma: no cover
        return self.response.text


class LoopringRequestException(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return 'LoopringRequestException: %s' % self.message


class LoopringOrderException(Exception):

    def __init__(self, code, message):
        self.code = code
        self.message = message

    def __str__(self):
        return 'LoopringOrderException(code=%s): %s' % (self.code, self.message)


class LoopringOrderMinAmountException(LoopringOrderException):

    def __init__(self, value):
        message = "Amount must be a multiple of %s" % value
        super(LoopringOrderMinAmountException, self).__init__(-1013, message)


class LoopringOrderMinPriceException(LoopringOrderException):

    def __init__(self, value):
        message = "Price must be at least %s" % value
        super(LoopringOrderMinPriceException, self).__init__(-1013, message)


class LoopringOrderMinTotalException(LoopringOrderException):

    def __init__(self, value):
        message = "Total must be at least %s" % value
        super(LoopringOrderMinTotalException, self).__init__(-1013, message)


class LoopringOrderUnknownSymbolException(LoopringOrderException):

    def __init__(self, value):
        message = "Unknown symbol %s" % value
        super(LoopringOrderUnknownSymbolException, self).__init__(-1013, message)


class LoopringOrderInactiveSymbolException(LoopringOrderException):

    def __init__(self, value):
        message = "Attempting to trade an inactive symbol %s" % value
        super(LoopringOrderInactiveSymbolException, self).__init__(-1013, message)


class LoopringWithdrawException(Exception):
    def __init__(self, message):
        if message == u'参数异常':
            message = 'Withdraw to this address through the website first'
        self.message = message

    def __str__(self):
        return 'LoopringWithdrawException: %s' % self.message
