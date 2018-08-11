#!/usr/bin/python3
#  -*- coding: utf-8 -*-

import os
import logging
import io

import args_parse

config_vars = {}
filename = os.path.expanduser("~") + "/.config/kimp3.cfg"

logging.info("Reading default args from " + filename)
whole_line = ""
for line in io.open(filename, "r+", encoding='utf8'):
    line = line.strip()
    if not line:
        continue
    if line[0] != '#':
        line = (line.split(' #'))[0]  # Избавляемся от коментов в конце строки

        # Собираем переносы строк в одну строку по бэкслэшу
        if line.endswith('\\'):
            whole_line += line[0:-1].rstrip()
            continue
        if whole_line != "":
            line = whole_line + line
            whole_line = ""

        varkey, varval = line.split('=')

        varval = varval.strip('\'\" ')
        varkey = varkey.strip()

        if varval.lower() == "yes":
            varval = True
        elif varval.lower() == "no":
            varval = False

        # Преобразуем строку в список
        if varkey in ['lastfm_banned_tags', 'bad_artists', 'common_files']:
            varval = list(map(lambda it: it.lower().strip(), varval.split(',')))

        logging.debug(str(varkey) + ": " + str(varval))
        config_vars[varkey] = varval

config_vars['scan_dir_list'] = map(lambda it: it.strip().rstrip('/'),
                                   list(config_vars['scan_dir_list'].split(',')))
config_vars['bad_artists'].append('')

# Самое сложное: превращаем строку в список списков
config_vars['lastfm_similar_tags'] = list(map(lambda it: it.strip('[]'),
                                              list(config_vars['lastfm_similar_tags'].split('],['))))
for i in range(0, len(config_vars['lastfm_similar_tags'])):
    config_vars['lastfm_similar_tags'][i] = map(lambda it: it.lower().strip(),
                                                list(config_vars['lastfm_similar_tags'][i].split(',')))

config_vars = args_parse.go(config_vars)


def get_config():
    return config_vars
