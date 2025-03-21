#  -*- coding: utf-8 -*-

# import taglib
import music_tag
import logging
from config import cfg, APP_NAME
# import eyed3

log = logging.getLogger(f"{APP_NAME}.{__name__}")


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
        try:
            file = music_tag.load_file(filepath)
        except Exception as e:
            log.error(e)
            file = None
        return file

    def get_tags(self):
        tags = dict(tracktitle=self.get_tag('tracktitle'),
                    album=self.get_tag('album'),
                    artist=self.get_tag('artist'),
                    albumartist=self.get_tag('albumartist'),

                    compilation=self.get_tag('compilation'),
                    genre=self.get_tag('genre'),
                    year=self.get_tag('year'),

                    discnumber=int(self.get_tag('discnumber')),
                    totaldiscs=int(self.get_tag('totaldiscs')),
                    tracknumber=int(self.get_tag('tracknumber')),
                    totaltracks=int(self.get_tag('totaltracks')),

                    # На случай, если проверки тегов не предвидится, нам всё равно нужны эти ключи
                    # discnumber='',
                    # totaldiscs='',
                    # tracknumber='',
                    # totaltracks='',

                    # play_count=self.file.tag.play_count,
                    comment=self.get_tag('comment'),
                    rating=self.get_comment('Rating'),
                    lastfm_tags=self.get_comment('LastFM tags'),
                    lyrics=self.get_tag('lyrics'))
        return tags

    def get_tag(self, tag):
        value = None
        try:
            value = self.file[tag].value  # [position]
        except KeyError:
            log.warning('No tag ' + tag + ' in ' + self.song.name)
        return value

    def get_comment(self, comment_id):
        try:
            values = self.file['comment'].values
            for v in values:
                if v.startswith(comment_id):
                    return v
        except Exception as e:
            log.error(e)
        return None

    def write_tags(self, tags_to_write='all'):
        if tags_to_write == 'all':
            for entry in self.new.keys():
                # if self.new[entry] is not None:
                self.write_one_tag(entry)
        else:
            self.write_one_tag(tags_to_write)

        # Сохраняем в файл
        self.file.save()
        return

    def write_one_tag(self, entry):
        if self.new[entry] == '' and entry in ['play_count']:
            self.new[entry] = 0

        if entry in ['track', 'album', 'artist', 'albumartist', 'compilation', 'genre',
                     'discnumber', 'totaldiscs', 'tracknumber', 'totaltracks', ]:
            self.file[entry] = self.new[entry]
        if entry == 'year':
            self.file[entry] = self.new[entry] if self.new[entry] != '' else None

        if entry == 'play_count':
            self.file[entry] = self.new[entry]

        if entry == 'rating':
            self.write_comment('Rating', self.new['rating'])

        if entry == 'lastfm_tags':
            self.write_comment('LastFM tags', self.new['lastfm_tags'])
        return

    def write_comment(self, comment_id, entry):
        try:
            values: list = self.file['comment'].values
            for v in values:
                if v.startswith(comment_id):
                    values.remove(v)
            values.append(f'{comment_id}: {entry}')
            self.file['comment'] = values
        except Exception as e:
            log.error(e)
