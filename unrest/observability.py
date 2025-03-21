import logging
import sys
from datetime import datetime, timezone

from pythonjsonlogger.jsonlogger import JsonFormatter

from unrest.context import context

loglevel = logging.INFO


def getLogger(name):
    log = logging.getLogger(name)
    log.setLevel(loglevel)

    for name, logger in logging.Logger.manager.loggerDict.items():
        # if name != '<module name>':
        #     logger.disabled = True
        try:
            logger.handlers.clear()
            logger.setLevel(loglevel)
        except:  # noqa
            pass

    return log


class Formatter(JsonFormatter):
    def formatTime(self, record, datefmt=None):
        for k, v in context._stack.peek.items():
            if not k.startswith("_"):
                record.__dict__[k] = v
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")


fmtstring = "%(name)s %(asctime)s %(levelname)s %(filename)s:%(lineno)s %(message)s"
mapping = {"name": "logger", "asctime": "timestamp", "levelname": "loglevel"}
formatter = Formatter(fmtstring, json_default=str, rename_fields=mapping)  # json_indent=2
logHandler = logging.StreamHandler(stream=sys.stderr)
logHandler.setLevel(loglevel)
logHandler.setFormatter(formatter)
logging.root.handlers = [logHandler]

logging.basicConfig(level=loglevel, handlers=[logHandler])
