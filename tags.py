#!/usr/bin/python3.6
#  -*- coding: utf-8 -*-

import taglib
import logging
logger = logging.getLogger(__name__)


class SongTags:

    def __init__(self, song):
        self.song = song
        self.file = taglib.File(song.filepath)
        self.tags = dict()

    def get_tags(self):
        self.tags = dict(song_title=self.get_tag('TITLE'),
                         album_title=self.get_tag('ALBUM'),
                         song_artist=self.get_tag('ARTIST'),
                         album_artist=self.get_tag('ALBUMARTIST'),

                         album_type=self.get_tag('CONTENTGROUP'),
                         genre=self.get_tag('GENRE'),
                         year=self.get_tag('DATE'),


                         disc_num_N=int(self.get_tag('DISCNUMBER').split('/')[0]),
                         num_of_discs_N=int(self.get_tag('DISCNUMBER').split('/')[1]),
                         track_num_N=int(self.get_tag('TRACKNUMBER')),
                         num_of_tracks_N=int(self.get_tag('NUMBEROFTRACKS')),

                         # На случай, если проверки тегов не предвидится, нам всё равно нужны эти ключи
                         disc_num='',
                         num_of_discs='',
                         track_num='',
                         num_of_tracks='',

                         play_count=self.mp3.tag.play_count,
                         comments=self.get_tag('COMMENT'),
                         rating=self.get_tag('COMMENT:RATING'),
                         lastfm_tags=self.get_tag('COMMENT:LASTFM TAGS'),
                         lyrics=self.get_tag('LYRICS'))

    def get_tag(self, tag, position=0):
        try:
            value = self.file.tags[tag][position]
        except KeyError as ke:
            logger.info('No tag ' + tag + ' in ' + self.song.name)
            value = ''
        return value
