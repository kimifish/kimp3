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
import re
from typing import List, Pattern

from kimp3.models import FileOperation
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


def _compile_patterns():
    """Compile regex patterns from config for better performance."""
    log.debug("Compiling regex patterns")
    
    # Compile banned_tags_patterns
    if hasattr(cfg.tags, 'banned_tags_patterns'):
        patterns: List[Pattern] = []
        for pattern in cfg.tags.banned_tags_patterns:
            try:
                patterns.append(re.compile(pattern))
            except re.error as e:
                log.warning(f"Invalid regex pattern '{pattern}': {e}")
        cfg.update('lastfm.banned_tags_patterns', patterns)
    
    # Compile similar_tags_patterns
    if hasattr(cfg.tags, 'similar_tags_patterns'):
        compiled_patterns_lists = []
        for pattern_list in cfg.tags.similar_tags_patterns:
            compiled_patterns = [pattern_list[0]] 
            for pattern in pattern_list[1:]:
                try:
                    compiled_patterns.append(re.compile(pattern))
                except re.error as e:
                    log.warning(f"Invalid regex pattern for '{pattern}': {e}")
            compiled_patterns_lists.append(compiled_patterns)
        cfg.update('lastfm.similar_tags_patterns', compiled_patterns_lists)

# Load config and compile patterns
args, unknown = _parse_args()
cfg.load_files([args.config_file])
cfg.load_args(unknown)

try:
    cfg.update('scan.move_or_copy', FileOperation(cfg.scan.move_or_copy))
except ValueError as e:
    log.error(f"Invalid configuration entry: scan.move_or_copy = {cfg.scan.move_or_copy}. Set to default 'copy'")
    cfg.update('scan.move_or_copy', FileOperation.COPY)

if cfg.tags.lastfm_api_key == '.env':
    cfg.update('tags.lastfm_api_key', os.getenv('LASTFM_API_KEY'))

if cfg.tags.lastfm_api_secret == '.env':
    cfg.update('tags.lastfm_api_secret', os.getenv('LASTFM_API_SECRET'))

if cfg.tags.discogs_token == '.env':
    cfg.update('tags.discogs_token', os.getenv('DISCOGS_TOKEN'))

if cfg.tags.genius_token == '.env':
    cfg.update('tags.genius_token', os.getenv('GENIUS_TOKEN'))

if not isinstance(cfg.scan.dir_list, list):
    cfg.update('scan.dir_list', [cfg.scan.dir_list])

cfg.update('runtime.console', console)

_compile_patterns()
_init_logs()

if __name__ == '__main__':
    # cfg.print_config()
    sys.exit(0)
