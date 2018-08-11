#!/usr/bin/python
#  -*- coding: utf-8 -*-

import argparse
import logging


def go(config_vars):
    logging.info(u"Parsing args")
    parser = argparse.ArgumentParser(description='Поиск, сортировка mp3 и обработка тэгов. '
                                                 'Значения по-умолчанию читаются из ~/.config/kimp3.conf')
    parser.add_argument("-s",
                        "--scan_dir",
                        type=str,
                        help="Каталог для поиска mp3-файлов")

    mv_or_cp = parser.add_mutually_exclusive_group()
    mv_or_cp.add_argument("-m",
                          "--move",
                          help="Переместить найденные файлы",
                          action="store_true")

    mv_or_cp.add_argument("-c",
                          "--copy",
                          help="Копировать найденные файлы",
                          action="store_true")

    parser.add_argument("-t",
                        "--check_tags",
                        help="Проверить и дополнить недостающие теги. По-умолчанию — " + str(config_vars[u'check_tags']),
                        default=config_vars[u'check_tags'],
                        action="store_true")

    parser.add_argument("-C",
                        "--is_compilation",
                        help="Проверить, не является ли альбом сборником. \n "
                             "Проверяет только альбомы по соотношению исполнителей. По-умолчанию — "
                             + str(config_vars[u'compilation_test']),
                        default=config_vars[u'compilation_test'],
                        action="store_true")

    parser.add_argument("-d",
                        "--decode",
                        help="Перекодировать тэги из lat1→utf8 в cp1251→utf8. Значение по-умолчанию — False",
                        action="store_true")

    parser.add_argument("-D",
                        "--dry",
                        help="Dry run",
                        action="store_true")

    parser.add_argument("-L",
                        "--log",
                        type=int,
                        help="Уровень логирования (0-5)")

    args = parser.parse_args()

    if args.log:
        if 0 <= args.log < 6:
            config_vars[u'log_level'] = args.log

    if args.scan_dir:
        config_vars[u'scan_dir_list'] = [args.scan_dir]
        logging.debug('scan_dir_list: ' + args.scan_dir, 'utf-8')

    if args.check_tags:
        config_vars[u'check_tags'] = True
        logging.debug(u"check_tags: " + str(config_vars[u'check_tags']))

    if args.copy:
        config_vars[u'move_or_copy'] = u'copy'
    elif args.move:
        config_vars[u'move_or_copy'] = u'move'
    logging.debug(u'move_or_copy: ' + config_vars[u'move_or_copy'])

    config_vars[u'decode'] = True if args.decode else False
    logging.debug(u"decode: " + str(config_vars[u'decode']))

    config_vars[u'dry run'] = True if args.dry else False
    logging.debug(u"dry run: " + str(config_vars[u'dry run']))

    return config_vars
