# -*- coding: utf-8 -*-

"""
    fuocore.engine
    ~~~~~~~~~~~~~~

    fuocore media player engine.
"""

from abc import ABCMeta, abstractmethod, abstractproperty
from enum import Enum
import logging
from queue import Queue
import random
import subprocess
import threading

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
        self._state = State.stopped
        self._duration = None

        self.position_changed = Signal()
        self.state_changed = Signal()
        self.song_changed = Signal()

    @property
    def state(self):
        """player state

        :return: :class:`fuocore.engine.State`
        """
        return self._state

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


class Player(object):
    """music player backend

    `mpg123 <https://www.mpg123.de/>`_ can read and execute commands from stdin
    when mpg123 activates its generic control interface by run ``mpg123 -R``.

    this music player backend do not implement a audio player itself. It use
    mpg123 as its actual audio player. It start mpg123 within a subprocess.
    send commands to mpg123's stdin to control mpg123 and get player state
    and extra info from mpg123's stdout through pipes.

    Each time the player play a song or switch a song, it will kill the
    old process and open a new subprocess.

    Simple usage::

        from fuocore import Player
        player = Player()
        url = 'test.mp3'  # can be a http url
        player.play(url)
    """
    def __init__(self):
        super().__init__()

        self._handler = None

        self._signal_queue = Queue()

        # parse mpg123 output and put signal into queue
        # this thread will be terminated when player is destroyed
        self._stdout_cap_thread = None

        self._ready_to_exit_flag = False

        self._position = 0
        self._state = State.stopped
        self._last_state = self._state
        self._duration = 0
        self._playback_mode = PlaybackMode.loop
        self._last_playback_mode = self._playback_mode

        # no repetition but ordering
        self._songs = []
        # current_song is None or `SongModel` instance and must in `_songs` list
        self._current_song = None

        self.finished = Signal()
        self.position_changed = Signal()
        self.state_changed = Signal()
        # emit `exit_signal` if player is ready to exit so that all
        # resource can be released properly, such as stoping threads and killing
        # subprocess.
        self.ready_to_exit = Signal()

        self.finished.connect(self.play_next)
        self.ready_to_exit.connect(self._ready_to_exit)

    @property
    def handler(self):
        if self._handler is None:
            try:
                self._handler = subprocess.Popen(['mpg123', '-R'],
                                                 stdin=subprocess.PIPE,
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE)
                self._stdout_cap_thread = threading.Thread(
                        target=self._capture_stdout, args=())
                self._stdout_cap_thread.start()
            except FileNotFoundError as e:
                raise RuntimeError('Cant find mpg123! Please install mpg123')
        return self._handler

    def _capture_stdout(self):
        while True:
            try:
                line = self._handler.stdout.readline().decode('utf8')
            except ValueError as e:
                break
            flag = line[:2]
            if flag == '@F':
                framecount, frame_left, sec, sec_left = line[3:].split(' ')
                self._position = float(sec)
                if int(framecount) == 0:
                    self._duration = float(sec_left)
                self.set_state(State.playing)
                self._signal_queue.put(self.position_changed)
            elif flag == '@P':
                a = line[3:4]
                if a == '0':
                    logging.info('Player stopped.')
                    self.set_state(State.stopped)
                    self._duration = 0
                    self._position = 0
                    self._signal_queue.put(self.finished)
                    break
                elif a == '1':
                    logging.info('Player paused.')
                    self.set_state(State.paused)
                else:
                    logging.info('Player resumed.')
                    self.set_state(State.playing)
            elif flag == '@E':
                logging.warning('Player error occured.')

    def run(self):
        while True:
            if self._ready_to_exit_flag:
                break
            signal = self._signal_queue.get()
            signal.emit()

    def _ready_to_exit(self):
        self._ready_to_exit_flag = True

    def shutdown(self):
        """stop signal-watch thread(worker)"""

        self.destroy()
        self._signal_queue.put(self.ready_to_exit)

    def destroy(self):
        """stop mpg123 and kill subprocess"""

        if self._handler is not None:
            try:
                self.handler.stdin.write(b'q\n')
                self.handler.stdin.flush()
                self.handler.stdin.close()
                self.handler.stdout.close()
                self.handler.stderr.close()
            except ValueError:
                pass
            self._stdout_cap_thread.join()
            self._stdout_cap_thread = None
            self.handler.wait()
            self.handler.kill()
            self._handler = None
        return True

    @property
    def position(self):
        return self._position

    @property
    def duration(self):
        return self._duration

    @property
    def state(self):
        return self._state

    @property
    def playback_mode(self):
        return self._playback_mode

    @property
    def current_song(self):
        return self._current_song

    @property
    def songs(self):
        return self._songs

    def play(self):
        if self.state == State.paused:
            self.toggle()
            return True
        return False

    def play_next(self):
        song = self.get_next_song()
        if song is not None:
            self.play_song(song)

    def play_last(self):
        song = self.get_previous_song()
        if song is not None:
            self.play_song(song)

    def toggle(self):
        self.handler.stdin.write(b'p\n')
        self.handler.stdin.flush()

    def pause(self):
        if self.state == State.playing:
            self.toggle()
            return True
        return False

    def stop(self):
        self.destroy()

    def set_state(self, state):
        self._state = state
        if self._last_state != state:
            self._signal_queue.put(self.state_changed)
            self._last_state = state

    def _play(self, url):
        self.destroy()
        cmd = 'L {0}\n'.format(url)
        self.handler.stdin.write(cmd.encode('utf8'))
        self.handler.stdin.flush()

    def play_song(self, song):
        self._play(song.url)
        self._current_song = song
        self.add_song(song)

    def play_songs(self, songs):
        self._songs = songs
        if self._songs:
            self.play_song(self._songs[0])

    def _get_song(self, song):
        '''get song instance in `_songs` list'''
        for i, m in enumerate(self._songs):
            if song.identifier == m.identifier:
                return song
        return None

    def add_song(self, song, insert=False):
        if self._get_song(song) is None:
            if insert:
                if self._current_song is None:
                    index = 0
                else:
                    current_index = self._songs.index(self._current_song)
                    index = current_index + 1
                self._songs.insert(index, song)
            else:
                self._songs.append(song)
            return True
        return False

    def remove_song(self, song):
        song = self._get_song(song)
        if song is None:
            return None
        self._songs.remove(song)
        return True

    def get_previous_song(self):
        if not self._songs:
            return None
        if self.playback_mode == PlaybackMode.one_loop:
            return self._current_song
        elif self.playback_mode == PlaybackMode.loop:
            current_index = self._songs.index(self._current_song)
            if current_index == 0:
                return self._songs[-1]
            else:
                return current_index - 1
        elif self.playback_mode == PlaybackMode.sequential:
            return None
        else:
            return random.choice(self._songs)

    def get_next_song(self):
        if not self._songs:
            return None
        if self.playback_mode == PlaybackMode.one_loop:
            return self._current_song
        elif self.playback_mode == PlaybackMode.loop:
            if self._current_song == self._songs[-1]:
                return self._songs[0]
            else:
                return self._songs[self._songs.index(self._current_song) + 1]
        elif self.playback_mode == PlaybackMode.sequential:
            self._signal_queue.put(self.signal_playlist_finished)
            return None
        else:
            return random.choice(self._songs)
