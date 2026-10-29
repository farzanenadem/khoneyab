import logging
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent.parent
__logger = None

class OneLineExceptionFormatter(logging.Formatter):
    def formatException(self, exc_info):
        result = super(OneLineExceptionFormatter, self).formatException(exc_info)
        return repr(result)  # or format into one line however you want to

    def format(self, record):
        s = super(OneLineExceptionFormatter, self).format(record)
        if record.exc_text:
            s = s.replace('\n+', ' ')
        return s


def get_logger(module_name='root'):
    global __logger
    if __logger is None:
        log_dir = ROOT_DIR / 'logs'
        log_dir.mkdir(exist_ok=True)

        formatter = OneLineExceptionFormatter(
            '%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(module)s.%(funcName)s(%(lineno)s): %(message)s',
            '%Y/%m/%d %H:%M:%S'
        )

        # file_handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1)
        file_handler = logging.FileHandler(log_dir / f'logs.log', 'a', 'utf-8')
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y%m%d"
        module_file_handler = logging.FileHandler(log_dir / f'{module_name}.log', 'a', 'utf-8')
        module_file_handler.setFormatter(formatter)
        module_file_handler.suffix = "%Y%m%d"
        # file_handler.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        # stream_handler.setLevel(logging.DEBUG)

        __logger = logging.getLogger(module_name)
        __logger.setLevel(logging.INFO)
        __logger.addHandler(file_handler)
        __logger.addHandler(module_file_handler)
        __logger.addHandler(stream_handler)
    return __logger
    