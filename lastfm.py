#!/usr/bin/python
#  -*- coding: utf-8 -*-
import logging
import pylast

# artist = network.get_artist("System of a Down")
# artist.shout("<3")
# track = network.get_track("Iron Maiden", "The Nomad")
# track.love()
# track.add_tags(("awesome", "favorite"))

# Type help(pylast.LastFMNetwork) or help(pylast) in a Python interpreter to get more help
# about anything and see examples of how it works
import conf_parse

logger = logging.getLogger('kimp3')
config_vars = conf_parse.get_config()

# Логинимся в Last.FM:
network = pylast.LastFMNetwork(api_key=config_vars[u'lastfm_API_KEY'],
                               api_secret=config_vars[u'lastfm_API_SECRET'],
                               username=config_vars[u'lastfm_username'],
                               password_hash=config_vars[u'lastfm_password_hash'])
logger.info(u'Last.FM login')


def get_track(tags):
    track = network.get_track(tags[u'song_artist'], tags[u'song_title'])
    return track


def get_artist(tags):
    artist = network.get_artist(tags[u'song_artist'])
    return artist


def get_album(tags):
    album = network.get_album(tags[u'album_artist'], tags[u'album_title'])
    return album


def get_tags(obj, num=10):
    try:
        lastfm_raw_tags = obj.get_top_tags()
    except pylast.WSError:
        logger.warning('Last.FM: Track not found')
        return set()

    lastfm_tags = set()
    for i in lastfm_raw_tags:
        tag = i.item.get_name().lower()
        for current_tag_list in config_vars[u'lastfm_similar_tags']:
            if tag in current_tag_list:
                tag = current_tag_list[0]
        if tag not in config_vars[u'lastfm_banned_tags']:
            lastfm_tags.add(tag)
    return lastfm_tags


def track_correction(track, tags):
    song_title = track.get_correction()
    if song_title != tags[u'song_title']:
        tags[u'song_title'] = song_title
        logger.info(u'Song title corrected to ' + song_title + u' by Last.FM')
    return tags


def artist_correction(artist, tags):
    song_artist = artist.get_correction()
    if song_artist != tags[u'song_artist']:
        tags[u'song_artist'] = song_artist
        logger.info(u'Artist name corrected to ' + tags[u'song_artist'] + u' by Last.FM')
    return tags


def album_correction(album, tags):
    album_title = album.get_correction()
    if album_title != tags[u'album_title']:
        tags[u'album_title'] = album_title
        logger.info(u'Album title corrected to ' + tags[u'album_title'] + u' by Last.FM')
    return tags
