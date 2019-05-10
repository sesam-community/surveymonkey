import logging
from paste.translogger import TransLogger


def get_stdout_handler():
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(format_string))
    return stdout_handler


def init_logger(logger_name, loglevel):
    logger = logging.getLogger(logger_name)

    # Log to stdout
    logger.addHandler(get_stdout_handler())
    logger.setLevel(loglevel)
    logger.propagate = False
    return logger


def get_level_name(loglevel):
    return logging.getLevelName(loglevel)


def add_access_logger(app, logger):
    wsgi_log_format_string = ('"%(REQUEST_METHOD)s %(REQUEST_URI)s %(HTTP_VERSION)s" '
                              '%(status)s %(bytes)s')

    app.wsgi_app = TransLogger(app.wsgi_app, logger_name=logger.name, format=wsgi_log_format_string,
                               setup_console_handler=False, set_logger_level=logger.level)
    app.logger.addHandler(get_stdout_handler())
    return app
