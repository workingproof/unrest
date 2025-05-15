import base64
import os
import sys
import dotenv

# We can't rely on tooling to do this properly, so force
dotenv.load_dotenv("%s.env" % os.environ.get("ENVIRONMENT", ""), override=True)


def is_under_test() -> bool:
    return "PYTEST_VERSION" in os.environ or "pytest" in sys.modules

def get(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key, None)
    if value is None or value == "":
        return default

    # if value.startswith("secret:"):
    #     (_, scheme, pointer) = value.split(":", 2)
    #     if scheme == "secretsmanager":
    #         client = get_boto_session().client("secretsmanager")
    #         secret = client.get_secret_value(SecretId=pointer)
    #         if "SecretString" in secret:
    #             return secret["SecretString"]
    #         else:
    #             return base64.b64decode(secret["SecretBinary"]).decode()
    #     else:
    #         raise RuntimeError("Bad secret scheme: %s" % scheme)
    # else:
    #     return str(value)
    return str(value)