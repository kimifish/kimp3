#!/usr/bin/python3
#  -*- coding: utf-8 -*-

import conf_parse
import pylast
import logging


# logger = logging.getLogger(__name__)
config_vars = conf_parse.get_config()

# Логинимся в Last.FM:
network = pylast.LastFMNetwork(api_key=config_vars[u'lastfm_API_KEY'],
                               api_secret=config_vars[u'lastfm_API_SECRET'],
                               username=config_vars[u'lastfm_username'],
                               password_hash=config_vars[u'lastfm_password_hash'])
# logger.info(u'Last.FM login')
