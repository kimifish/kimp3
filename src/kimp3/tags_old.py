#!/usr/bin/python3.6
#  -*- coding: utf-8 -*-

# import taglib
import music_tag
import logging
import eyed3


log = logging.getLogger(__name__)


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
        if cfg.tag_reader == 'eyed3':
            file = eyed3.load(filepath)
        elif cfg.tag_reader == 'music_tag':
            file = music_tag.load_file(filepath)
        else:
            log.error("Incorrect tags library in config. Must be taglib or eyed3.")
            quit()
        return file

    def get_tags(self):
        tags = None
        # Открываем файл библятекой глаз3
        if cfg.tag_reader == 'eyed3':
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
                            lastfm_tags=self.file.tag.comments.get("LastFM tags").text if self.file.tag.comments.get("LastFM tags") else "",
                            lyrics=self.file.tag.lyrics)
            except AttributeError as ae:
                log.warning(str(self.file) + ': ' + str(ae))

        elif cfg.tag_reader == 'music_tag':
            tags = dict(song_title=self.get_tag('tracktitle'),
                        album_title=self.get_tag('album'),
                        song_artist=self.get_tag('artist'),
                        album_artist=self.get_tag('albumartist'),

                        album_type=self.get_tag('compilation'),
                        genre=self.get_tag('genre'),
                        year=self.get_tag('year'),

                        disc_num_N=int(self.get_tag('discnumber')),
                        num_of_discs_N=int(self.get_tag('totaldiscs')),
                        track_num_N=int(self.get_tag('tracknumber')),
                        num_of_tracks_N=int(self.get_tag('totaltracks')),

                        # На случай, если проверки тегов не предвидится, нам всё равно нужны эти ключи
                        disc_num='',
                        num_of_discs='',
                        track_num='',
                        num_of_tracks='',

                        # play_count=self.file.tag.play_count,
                        comments=self.get_tag('comment'),
                        rating=self.get_tag('comment', 'Rating'),
                        lastfm_tags=self.get_tag('comment', 'LastFM tags'),
                        lyrics=self.get_tag('LYRICS'))
        return tags

    def get_tag(self, tag, starts_with=None):
        value = None
        try:
            if not starts_with:
                value = self.file[tag].value  # [position]
            else:
                for v in self.file[tag].values:
                    if v.startswith(starts_with):
                        value = v.split(':')[1]
                        continue
        except KeyError:
            log.warning('No tag ' + tag + ' in ' + self.song.name)
        return value

    def write_tags(self, tags_to_write='all'):
        if tags_to_write == 'all':
            for entry in self.new.keys():
                # if self.new[entry] is not None:
                self.write_one_tag(entry)
        else:
            self.write_one_tag(tags_to_write)

        # Сохраняем в файл
        if cfg.tag_reader == 'eyed3':
            self.file.tag.save(encoding='utf-8')
        elif cfg.tag_reader == 'music_tag':
            self.file.save()
        return

    def write_one_tag(self, entry):
        if self.new[entry] == '' and entry in ['play_count']:
            self.new[entry] = 0

        if entry == 'song_title':
            self.file.tag.title = self.new[entry]
        if entry == 'album_title':
            self.file.tag.album = self.new[entry]

        if entry == 'song_artist':
            self.file.tag.artist = self.new[entry]
        if entry == 'album_artist':
            self.file.tag.album_artist = self.new[entry]

        if entry == 'album_type':
            self.file.tag.album_type = self.new[entry]
        if entry == 'genre':
            self.file.tag.genre = self.new[entry]
        if entry == 'year':
            self.file.tag.release_date = self.new[entry] if self.new[entry] != '' else None

        # Смысл всей этой заморочки с номерами дисков и треков в том,
        # что eyed3 здесь всегда общается только с _N версиями тегов (int), тогда как пользователь
        # по задумке должен взаимодействовать со строковым значением (лидирующие нули, все дела).
        if entry == 'disc_num' or 'num_of_discs':
            self.new['num_of_discs_N'] = int(self.new['num_of_discs']) \
                if self.new['num_of_discs'] != '' \
                else None
            self.new['disc_num_N'] = int(self.new['disc_num']) \
                if self.new['disc_num'] != '' \
                else None
            self.file.tag.disc_num = (self.new['disc_num_N'], self.new['num_of_discs_N'])

        if entry == 'track_num' or 'num_of_tracks':
            self.new['num_of_tracks_N'] = int(self.new['num_of_tracks']) \
                if self.new['num_of_tracks'] != '' or None \
                else None
            self.new['track_num_N'] = int(self.new['track_num']) \
                if self.new['track_num'] != '' or None \
                else None
            self.file.tag.track_num = (self.new['track_num_N'], self.new['num_of_tracks_N'])

        if entry == 'play_count':
            self.file.tag.play_count = self.new[entry]

        if entry == 'rating':
            self.file.tag.comments.set(self.new['rating'], 'Rating')

        if entry == 'lastfm_tags':
            self.file.tag.comments.set(self.new['lastfm_tags'], 'LastFM tags')

        # Здесь что-то не так, там объекты какие-то передаются...
        # Стоит видимо заглянуть сюда: http://eyed3.nicfit.net/_modules/eyed3/id3/tag.html#Tag.comments

        # if entry == 'comments':
        #     self.mp3.tag.comments = self.tags[entry]
        # if entry == 'lyrics':
        #     self.mp3.tag.lyrics = self.tags[entry]
        # print entry + ": "
        # print self.tags[entry]
        # print type(self.tags[entry])

        return
