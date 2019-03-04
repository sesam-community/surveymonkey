import logging

def Logger(logger_name, loglevel):
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logger = logging.getLogger(logger_name)

    # Log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(stdout_handler)
    logger.setLevel(loglevel)
    return logger

def getLevel(logger):
    return logging.getLevelName(logger.level)    
