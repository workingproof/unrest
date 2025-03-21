import base64
import os

import dotenv

from unrest.utils import singleton

_is_testing = False


@singleton
def get_boto_session():
    import boto3

    return boto3.session.Session()


# We can't rely on tooling to do this properly, so force
dotenv.load_dotenv("%s.env" % os.environ.get("UNREST_ENVIRONMENT", ""), override=True)


def is_under_test(value: bool = None):
    global _is_testing
    if value is not None:
        _is_testing = value
    return _is_testing


def get(key: str, default: str = None) -> str:
    value = os.environ.get(key, None)
    if value is None or value == "":
        return default

    if value.startswith("secret:"):
        (_, scheme, pointer) = value.split(":", 2)
        if scheme == "secretsmanager":
            client = get_boto_session().client("secretsmanager")
            secret = client.get_secret_value(SecretId=pointer)
            if "SecretString" in secret:
                return secret["SecretString"]
            else:
                return base64.b64decode(secret["SecretBinary"]).decode()
        else:
            raise RuntimeError("Bad secret scheme: %s" % scheme)
    else:
        return str(value)
