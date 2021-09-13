import logging

def init_logging():
    logger = logging.getLogger("zwebsocket")
    handler = logging.StreamHandler()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt='[%(asctime)s][%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

init_logging()

def get_logger(name):
    logger = logging.getLogger(name)
    return logger