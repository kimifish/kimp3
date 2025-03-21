#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import os
import sys
import rich.console
import argparse
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback 
from dotenv import load_dotenv
from kimiconfig import Config
cfg = Config(use_dataclasses=True)
install_rich_traceback(show_locals=True)

APP_NAME = 'kimp3'
HOME_DIR = os.path.expanduser("~")
DEFAULT_CONFIG_FILE = os.path.join(
    os.getenv("XDG_CONFIG_HOME", os.path.join(HOME_DIR, ".config")), 
    APP_NAME, 
    "config.yaml")

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.NOTSET,
    format="%(message)s",
    datefmt="%X",
    handlers=[RichHandler(console=Console(), markup=True)],
)
parent_logger = logging.getLogger(APP_NAME)
log = logging.getLogger(f'{APP_NAME}.{__name__}')
console = rich.console.Console(color_system='truecolor', width=120)
rich_handler = RichHandler(rich_tracebacks=True,
                           markup=True,
                           show_path=True,
                           tracebacks_show_locals=True,
                           console=console)


def _init_logs():
    """Initialize logging configuration.
    
    Checks if required config dataclasses exist before accessing them.
    Falls back to default values if they don't.
    """
    # Check if logging config exists
    if not hasattr(cfg, 'logging'):
        log.warning("No logging configuration found, using defaults")
        return

    # Check and set suppressed loggers
    if (hasattr(cfg.logging, 'loggers') and 
        hasattr(cfg.logging.loggers, 'suppress') and 
        hasattr(cfg.logging.loggers, 'suppress_level')):
        for logger_name in cfg.logging.loggers.suppress:
            logging.getLogger(logger_name).setLevel(
                getattr(logging, cfg.logging.loggers.suppress_level)
            )
    else:
        log.warning("No logger suppression configuration found")

    # Check and set root logger level
    if hasattr(cfg.logging, 'level'):
        try:
            parent_logger.setLevel(cfg.logging.level)
            if cfg.logging.level == "DEBUG":
                cfg.print_config()
        except (ValueError, AttributeError) as e:
            log.warning(f"Invalid logging level configuration: {e}")
            parent_logger.setLevel(logging.INFO)
    else:
        log.warning("No logging level configuration found, using INFO")
        parent_logger.setLevel(logging.INFO)


def _parse_args():
    log.info("Parsing args")
    parser = argparse.ArgumentParser(description='Поиск, сортировка mp3 и обработка тэгов. '
                                                 'Значения по-умолчанию читаются из ~/.config/kimp3/config.yaml')
    parser.add_argument(
        "-c",
        "--config",
        dest="config_file",
        default=DEFAULT_CONFIG_FILE,
        help="Configuration file location.",
    )
    parser.add_argument("-s",
                        "--scan_dir",
                        type=str,
                        help="Каталог для поиска mp3-файлов")

    parser.add_argument("-d",
                        "--decode",
                        help="Перекодировать тэги из lat1→utf8 в cp1251→utf8. Значение по-умолчанию — False",
                        action="store_true")

    parser.add_argument("-D",
                        "--dry",
                        help="Dry run",
                        action="store_true")

    args, unknown = parser.parse_known_args()

    cfg.update('decode', True if args.decode else False)
    cfg.update('dry_run', True if args.dry else False)
    
    return args, unknown


args, unknown = _parse_args()
cfg.load_files([args.config_file])
cfg.load_args(unknown)

if cfg.lastfm.api_key == '.env':
    cfg.update('lastfm.api_key', os.getenv('LASTFM_API_KEY'))
if cfg.lastfm.api_secret == '.env':
    cfg.update('lastfm.api_secret', os.getenv('LASTFM_API_SECRET'))
if not isinstance(cfg.scan.dir_list, list):
    cfg.update('scan.dir_list', [cfg.scan.dir_list])

_init_logs()

if __name__ == '__main__':
    cfg.print_config()
    sys.exit(0)
