import pyotp
import robin_stocks
import yaml

LOGIN_EXPIRATION_SECS = 60 * 60 * 24 * 7  # 1 week


def robinhood_auth():
    with open('credentials.yml', 'r') as credentials_file:
        credentials = yaml.safe_load(credentials_file)

    rh_credentials = credentials.get('robinhood')
    if rh_credentials:
        otp_secret = rh_credentials.get('otp_secret')
        otp = pyotp.TOTP(otp_secret).now() if otp_secret else None

        try:
            robin_stocks.robinhood.login(
                rh_credentials['username'],
                rh_credentials['password'],
                LOGIN_EXPIRATION_SECS,
                mfa_code=otp
            )
            return True
        except Exception as err:
            print(err)
            return False

    return False
