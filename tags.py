#!/usr/bin/python3.6
#  -*- coding: utf-8 -*-

import taglib
import logging
import conf_parse
import eyed3

config_vars = conf_parse.get_config()

logger = logging.getLogger(__name__)


class SongTags:

    def __init__(self, filepath, tags=None):
        self.song = filepath
        self.file = self.open_file(filepath)
        if not tags:
            self.old = self.get_tags()
        else:
            self.old = tags
        self.new = self.old.copy()

    @staticmethod
    def open_file(filepath):
        file = None
        if config_vars['tag_reader'] == 'eyed3':
            file = eyed3.load(filepath)
        elif config_vars['tag_reader'] == 'taglib':
            file = taglib.File(filepath)
        else:
            logger.error("Incorrect tags library in config. Must be taglib or eyed3.")
            quit()
        return file

    def get_tags(self):
        tags = None
        # Открываем файл библятекой глаз3
        if config_vars['tag_reader'] == 'eyed3':
            try:
                tags = dict(song_title=self.file.tag.title,
                            album_title=self.file.tag.album,
                            song_artist=self.file.tag.artist,
                            album_artist=self.file.tag.album_artist,

                            album_type=self.file.tag.album_type,
                            genre=self.file.tag.genre.name if self.file.tag.genre is not None else '',
                            year=self.file.tag.best_release_date,

                            disc_num_N=self.file.tag.disc_num[0],
                            num_of_discs_N=self.file.tag.disc_num[1],
                            track_num_N=self.file.tag.track_num[0],
                            num_of_tracks_N=self.file.tag.track_num[1],

                            # На случай, если проверки тегов не предвидится, нам всё равно нужны эти ключи
                            disc_num='',
                            num_of_discs='',
                            track_num='',
                            num_of_tracks='',

                            play_count=self.file.tag.play_count,
                            comments=self.file.tag.comments,
                            rating=self.file.tag.comments.get("Rating"),
                            lastfm_tags=self.file.tag.comments.get("LastFM tags"),
                            lyrics=self.file.tag.lyrics)
            except AttributeError as ae:
                logger.warning(str(self.file) + ': ' + str(ae))

        elif config_vars['tag_reader'] == 'taglib':
            tags = dict(song_title=self.get_tag('TITLE'),
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

                        # play_count=self.file.tag.play_count,
                        comments=self.get_tag('COMMENT'),
                        rating=self.get_tag('COMMENT:RATING'),
                        lastfm_tags=self.get_tag('COMMENT:LASTFM TAGS'),
                        lyrics=self.get_tag('LYRICS'))
        return tags

    def get_tag(self, tag, position=0):
        try:
            value = self.file.tags[tag][position]
        except KeyError:
            logger.info('No tag ' + tag + ' in ' + self.song.name)
            value = ''
        return value

    def write_tags(self, tags_to_write=u'all'):
        if tags_to_write == u'all':
            for entry in self.new.keys():
                # if self.new[entry] is not None:
                self.write_one_tag(entry)
        else:
            self.write_one_tag(tags_to_write)

        # Сохраняем в файл
        if config_vars['tag_reader'] == 'eyed3':
            self.file.tag.save(encoding='utf-8')
        elif config_vars['tag_reader'] == 'taglib':
            self.file.save()
        return

    def write_one_tag(self, entry):
        if self.new[entry] == u'' and entry in [u'play_count']:
            self.new[entry] = 0

        if entry == u'song_title':
            self.file.tag.title = self.new[entry]
        if entry == u'album_title':
            self.file.tag.album = self.new[entry]

        if entry == u'song_artist':
            self.file.tag.artist = self.new[entry]
        if entry == u'album_artist':
            self.file.tag.album_artist = self.new[entry]

        if entry == u'album_type':
            self.file.tag.album_type = self.new[entry]
        if entry == u'genre':
            self.file.tag.genre = self.new[entry]
        if entry == u'year':
            self.file.tag.release_date = self.new[entry] if self.new[entry] != u'' else None

        # Смысл всей этой заморочки с номерами дисков и треков в том,
        # что eyed3 здесь всегда общается только с _N версиями тегов (int), тогда как пользователь
        # по задумке должен взаимодействовать со строковым значением (лидирующие нули, все дела).
        if entry == u'disc_num' or u'num_of_discs':
            self.new[u'num_of_discs_N'] = int(self.new[u'num_of_discs']) \
                if self.new[u'num_of_discs'] != u'' \
                else None
            self.new[u'disc_num_N'] = int(self.new[u'disc_num']) \
                if self.new[u'disc_num'] != u'' \
                else None
            self.file.tag.disc_num = (self.new[u'disc_num_N'], self.new[u'num_of_discs_N'])

        if entry == u'track_num' or u'num_of_tracks':
            self.new[u'num_of_tracks_N'] = int(self.new[u'num_of_tracks']) \
                if self.new[u'num_of_tracks'] != u'' or None \
                else None
            self.new[u'track_num_N'] = int(self.new[u'track_num']) \
                if self.new[u'track_num'] != u'' or None \
                else None
            self.file.tag.track_num = (self.new[u'track_num_N'], self.new[u'num_of_tracks_N'])

        if entry == u'play_count':
            self.file.tag.play_count = self.new[entry]

        if entry == u'rating':
            self.file.tag.comments.set(self.new[u'rating'], u'Rating')

        if entry == u'lastfm_tags':
            self.file.tag.comments.set(self.new[u'lastfm_tags'], u'LastFM tags')

        # Здесь что-то не так, там объекты какие-то передаются...
        # Стоит видимо заглянуть сюда: http://eyed3.nicfit.net/_modules/eyed3/id3/tag.html#Tag.comments

        # if entry == u'comments':
        #     self.mp3.tag.comments = self.tags[entry]
        # if entry == u'lyrics':
        #     self.mp3.tag.lyrics = self.tags[entry]
        # print entry + ": "
        # print self.tags[entry]
        # print type(self.tags[entry])

        return
