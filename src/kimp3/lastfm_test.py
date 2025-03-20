#!/usr/bin/python3
#  -*- coding: utf-8 -*-

import pylast
import logging
from config import cfg


logger = logging.getLogger(__name__)
# config_vars = conf_parse.get_config()

# Логинимся в Last.FM:
network = pylast.LastFMNetwork(api_key=cfg.lastfm_API_KEY,
                               api_secret=cfg.lastfm_API_SECRET,
                               username=cfg.lastfm_username,
                               password_hash=cfg.lastfm_password_hash,
                               )
# logger.info(u'Last.FM login')
