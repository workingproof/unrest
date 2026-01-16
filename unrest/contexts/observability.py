import logging
import sys
from datetime import datetime, timezone

from pythonjsonlogger.jsonlogger import JsonFormatter

loglevel = logging.INFO
otherlevel = logging.ERROR


class Formatter(JsonFormatter):
    def formatTime(self, record, datefmt=None):
        from unrest.contexts import context
        ctx = context._ctx
        usr = ctx.user
        record.__dict__.update({
            "context": {"id": ctx.id, "entrypoint": ctx._entrypoint, "mutation": ctx._global, "properties": { k: v for (k,v) in ctx._vars.items() if not k.startswith("_")} },
            "user": {"id": usr.identity, "display_name": usr.display_name, "properties": usr.props},
        })
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")


fmtstring = "%(name)s %(asctime)s %(levelname)s %(filename)s:%(lineno)s %(message)s"
mapping = {"name": "logger", "asctime": "timestamp", "levelname": "loglevel"}
formatter = Formatter(fmtstring, json_default=str, rename_fields=mapping)  # json_indent=2
logHandler = logging.StreamHandler(stream=sys.stderr)
logHandler.setLevel(loglevel)
logHandler.setFormatter(formatter)
logging.root.handlers = [logHandler]

logging.basicConfig(level=loglevel, handlers=[logHandler])

_loggers = {}

def getLogger(name):
    log = logging.getLogger(name)
    log.setLevel(loglevel)
    _loggers[name] = log

    for name, logger in logging.Logger.manager.loggerDict.items():
        if name not in _loggers:
            # logger.disabled = True
            try:
                if hasattr(logger, "handlers"):
                    logger.handlers.clear()
                    logger.addHandler(logHandler)
                logger.setLevel(otherlevel)
            except:  # noqa
                pass

    return log
