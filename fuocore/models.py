# -*- coding: utf-8 -*-


from april import Struct


class BaseModel(Struct):
    _fields = ['source', 'identifier']


class BriefArtistModel(BaseModel):
    _fields = ['name', 'img']


class BriefAlbumModel(BaseModel):
    _fields = ['name']


class BriefSongModel(BaseModel):
    _fields = ['title', 'url', 'duration', 'brief_album', 'brief_artists']


class ArtistModel(BriefArtistModel):
    _fields = ['songs', 'desc']


class AlbumModel(BriefAlbumModel):
    _fields = ['img', 'songs', 'artists', 'desc']


class LyricModel(BaseModel):
    _fields = ['song', 'content', 'trans_content']


class SongModel(BriefSongModel):
    _fields = ['album', 'artists']

    def __repr__(self):
        return '<{} source={} identifier={}>'.format(
            self.__class__.__name__, self.source, self.identifier)

    def __str__(self):
        return 'fuo://{}/songs/{}'.format(self.source, self.identifier)  # noqa
