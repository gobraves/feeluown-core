# -*- coding: utf-8 -*-

"""
    fuocore.engine
    ~~~~~~~~~~~~~~

    fuocore media player engine.
"""

from abc import ABCMeta, abstractmethod
from enum import Enum
import random

from .dispatch import Signal


class State(Enum):
    """Player state"""

    stopped = 0
    paused = 1
    playing = 2


class PlaybackMode(Enum):
    one_loop = 0
    sequential = 1
    loop = 2
    random = 3


class Playlist(object):
    """player playlist provide a list of song model to play"""

    def __init__(self, songs=[], playback_mode=PlaybackMode.loop):
        """

        :param songs: list of :class:`fuocore.models.SongModel`
        :param playback_mode: :class:`fuocore.player.PlaybackMode`
        """
        self._last_index = None
        self._current_index = None
        self._songs = songs
        self._playback_mode = playback_mode

        # signals
        self.playback_mode_changed = Signal()
        self.song_changed = Signal()

    @property
    def current_song(self):
        if self._current_index is None:
            return None
        return self._songs[self._current_index]

    @current_song.setter
    def current_song(self, song):
        """change current song, emit song changed singal"""

        # add it to playlist if song not in playlist
        if song in self._songs:
            index = self._songs.index(song)
        else:
            if self._current_index is None:
                index = 0
            else:
                index = self._current_index + 1
            self._songs.insert(index, song)
        self._last_song = self.current_song
        self._current_index = index
        self.song_changed.emit()

    @property
    def playback_mode(self):
        return self._playback_mode

    @playback_mode.setter
    def playback_mode(self, playback_mode):
        self._playback_mode = playback_mode
        self.playback_mode_changed.emit()

    def next(self):
        """advance to next song"""
        if not self._songs:
            return

        if self.current_song is None:
            self._current_index = 0
            self.song_changed.emit()
            return

        if self.playback_mode in (PlaybackMode.one_loop, PlaybackMode.loop):
            if self._current_index == len(self._songs) - 1:
                self._current_index = 0
            self._current_index += 1
        elif self.playback_mode == PlaybackMode.sequential:
            if self._current_index == len(self._songs) - 1:
                self._current_index = None
            self._current_index += 1
        else:
            self._current_index = random.choice(range(0, len(self._songs)))

        self.song_changed.emit()

    def previous(self):
        """return to previous played song, if previous played song not exists, get the song
        before current song in playback mode order.
        """
        if not self._songs:
            return None

        if self._last_index is not None:
            self._current_index = self._last_index
            self.song_changed.emit()
            return

        if self._current_index is None:
            self._current_index = 0
            self.song_changed.emit()
            return

        if self.playback_mode == PlaybackMode.random:
            self._current_index = random.choice(range(0, len(self._songs)))
        else:
            self._current_index -= 1

        self.song_changed.emit()


class AbstractPlayer(object, metaclass=ABCMeta):

    def __init__(self , *args, **kwargs):
        self._position = 0
        self._playlist = None
        self._song = None
        self.__state = State.stopped
        self._duration = None

        self.position_changed = Signal()
        self.state_changed = Signal()
        self.song_changed = Signal()

    @property
    def state(self):
        """player state

        :return: :class:`fuocore.engine.State`
        """
        return self.__state

    @state.setter
    def state(self, value):
        self.__state = value
        self.state_changed.emit()

    @property
    def current_song(self):
        return self._song

    @property
    def playlist(self):
        """player playlist

        :return: :class:`fuocore.engine.Playlist`
        """
        return self._playlist

    @playlist.setter
    def playlist(self, playlist):
        self._playlist = playlist

    @property
    def position(self):
        """player position, the units is mileseconds"""
        return self._position

    @position.setter
    def position(self, position):
        self._position = position

    @property
    def duration(self):
        """player media duration, the units is mileseconds"""
        return self._duration

    @abstractmethod
    def play(self, url):
        """play media

        :param url: a local file absolute path, or a http url that refers to a
            media file
        """

    @abstractmethod
    def play_song(self, song):
        """play media by song model

        :param song: :class:`fuocore.models.SongModel`
        """

    @abstractmethod
    def resume(self):
        """play playback"""

    @abstractmethod
    def pause(self):
        """pause player"""

    @abstractmethod
    def toggle(self):
        """toggle player state"""

    @abstractmethod
    def stop(self):
        """stop player"""

    @abstractmethod
    def initialize(self):
        """"initialize player"""

    @abstractmethod
    def quit(self):
        """quit player, do some clean up here"""
