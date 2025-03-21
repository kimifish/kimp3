#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false


import logging
import pylast
from config import cfg, APP_NAME

# artist = network.get_artist("System of a Down")
# artist.shout("<3")
# track = network.get_track("Iron Maiden", "The Nomad")
# track.love()
# track.add_tags(("awesome", "favorite"))

# Type help(pylast.LastFMNetwork) or help(pylast) in a Python interpreter to get more help
# about anything and see examples of how it works

log = logging.getLogger(f"{APP_NAME}.{__name__}")

# Логинимся в Last.FM:
network = pylast.LastFMNetwork(api_key=cfg.lastfm.api_key,
                               api_secret=cfg.lastfm.api_secret,
                               username=cfg.lastfm.username,
                               password_hash=cfg.lastfm.password_hash)
log.info(u'Last.FM login')


def get_track(tags):
    track = network.get_track(tags['song_artist'], tags['song_title'])
    return track


def get_artist(tags):
    artist = network.get_artist(tags['song_artist'])
    return artist  # TODO: добавить сюда теги, и сделать, чтобы они участвовали в жанре


def get_album(tags):
    album = network.get_album(tags['album_artist'], tags['album_title'])
    return album


def get_genre(album, artist):
    genre = get_tags(album, 5, 10)
    artist_genre = get_tags(artist, 5, 10)
    for g in artist_genre:
        if g not in genre:
            genre.append(g)

    if len(genre) > 5:
        genre = genre[0:4]
    genre = ", ".join(genre)
    return genre.title()


def get_tags(obj, num=20, min_weight=1):  # TODO: не учитывать теги с весом 10 и менее (примерно)
    try:
        lastfm_raw_tags = obj.get_top_tags()
    except pylast.WSError:
        log.warning('Last.FM: Track not found')
        return set()

    lastfm_tags = []
    for i in lastfm_raw_tags:
        if int(i.weight) < min_weight:
            pass
        tag = i.item.get_name().lower()
        for current_tag_list in cfg.lastfm_similar_tags:
            current_tag_list = list(current_tag_list)
            if tag in current_tag_list:
                tag = current_tag_list[0]
        if tag not in cfg.lastfm_banned_tags:
            lastfm_tags.append(tag)
    return lastfm_tags[0:num]


def track_correction(track, tags):
    song_title = track.get_correction()
    if song_title and song_title != tags['song_title']:
        tags['song_title'] = song_title
        log.info('Song title corrected to ' + song_title + ' by Last.FM')
    return tags


def artist_correction(artist, tags):
    song_artist = artist.get_correction()
    if song_artist and song_artist != tags['song_artist']:
        tags['song_artist'] = song_artist
        log.info('Artist name corrected to ' + tags['song_artist'] + ' by Last.FM')
    return tags


def album_correction(album, tags):
    album_title = album.get_correction()
    if album_title and album_title != tags['album_title']:
        tags['album_title'] = album_title
        log.info('Album title corrected to ' + tags['album_title'] + ' by Last.FM')
    return tags


def genre_correction(genre, tags):
    if genre != tags['genre'] and genre != '':
        tags['genre'] = genre
        log.info('Genre corrected to ' + tags['genre'] + ' by Last.FM')
    return tags
