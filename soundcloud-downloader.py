#!/usr/bin/env python3

from progressbar import AdaptiveTransferSpeed, ProgressBar, Bar, Percentage, DataSize, SimpleProgress
from progressbar.widgets import WidgetBase
import string
import requests
import json
import argparse
import sys
import urllib
import mutagen
import mutagen.mp3
import os
import re
import platform
from mutagen.easyid3 import EasyID3

CLIENTID = '02gUJC0hH2ct1EGOcYXQIzRFU91c72Ea'
SKIPREGEX = re.compile('[[{(]clip|[[{(]preview|[[({]forthcoming', re.IGNORECASE)
MINLENGTH = 121  # seconds


def resolve_profile_tracks_url(friendly_url):
    r = requests.get('http://api.soundcloud.com/resolve.json?url=http://soundcloud.com/{}/tracks&client_id={}'.format(friendly_url, CLIENTID), allow_redirects=False)

    if 'errors' in json.loads(r.text):
        print('Cannot find the specified user: {}'.format(json.loads(r.text)['errors'][0]['error_message']))
        sys.exit(1)
    else:
        resolved_profile_uri = json.loads(r.text)['location']
        return resolved_profile_uri

def get_profile_info(friendly_url):
    r = requests.get('http://api.soundcloud.com/resolve.json?url=http://soundcloud.com/{}/&client_id={}'.format(friendly_url, CLIENTID), allow_redirects=False)

    if 'errors' in json.loads(r.text):
        print('Cannot find the specified user: {}'.format(json.loads(r.text)['errors'][0]['error_message']))
        sys.exit(1)
    else:
        userurl = json.loads(r.text)['location']
        s = requests.get(userurl, allow_redirects=False)

        if 'errors' in json.loads(s.text):
            sys.exit(1)
        else:
            return json.loads(s.text)


def get_profile_tracks_pbar(tracks_url, tracks_num):
    tracks = []
    npages = int(tracks_num / 200) + 1
    pbar = ProgressBar(widgets=['Fetching page ', SimpleProgress()])
    for pagenum in pbar(range(0, npages)):
        r = requests.get(
            tracks_url + '&limit=200&offset={}'.format(200 * pagenum))
        pagetracks = json.loads(r.text)
        tracks.extend(pagetracks)
    return tracks

def get_profile_tracks(tracks_url):
    r = requests.get(tracks_url + '&limit=200')
    pagetracks = json.loads(r.text)
    return pagetracks

def sanitize_name(name):
    # First, strip non-printable characters
    name = ''.join(s for s in name if s in string.printable)

    # Now replace illegal filename characters
    prohibited_chars = ['<', '>', '"', '|', ':', '*', '?', '\\', '/']
    subst_char = '_'
    for char in prohibited_chars:
        name = name.replace(char, subst_char)

    return name


class fillHalf(WidgetBase):
    'Custom widget for progressbar to make text span half of the console'

    def __init__(self, text, **kwargs):
        self.text = text

    def __call__(self, progress, data):
        width = str(int(progress.term_width * 0.4))
        formatstr = '{0:<' + width + '.' + width + '}'
        return formatstr.format(self.text)


def download_tracks(tracks, directory):
    dltracks = []
    dups = 0
    previews = 0
    # No ETA, progressbar.ETA() is unstable
    DLwidgets = [DataSize(), '  ', AdaptiveTransferSpeed(), ' ', Bar(), Percentage()]
    for track in tracks:
        name = sanitize_name(track['title'])
        filename = name + '.mp3'
        filename = os.path.join(directory, filename)
        if os.path.isfile(filename):
            dups += 1
        elif SKIPREGEX.search(track['title']) or track['duration'] <= MINLENGTH*1000:
            previews += 1
        else:
            track['dispname'] = name
            track['filename'] = filename
            dltracks.append(track)

    num = len(dltracks)
    reportstr = '{} tracks already downloaded, {} previews skipped, {} tracks to download.'
    print(reportstr.format(dups, previews, num))

    for i, track in enumerate(dltracks):

        tempfile_name = track['filename'] + '.part'

        dispstr = '({} / {}) {}'.format(i + 1, num, track['dispname'])

        download_url = track['stream_url'] + '?client_id={}'.format(CLIENTID)
        try:
            u = requests.get(download_url, stream=True)
        except urllib.error.URLError as e:
            # Print error and keep going
            print('Error downloading {}: {} {}'.format(track['dispname'], e.code, e.reason))
            print('URL was ' + download_url)

        f = open(tempfile_name, 'wb')
        file_size = int(u.headers.get('Content-Length'))

        dlbar = ProgressBar(max_value=file_size, widgets=[fillHalf(dispstr), ' ', *DLwidgets]).start()
        file_size_dl = 0
        block_sz = 8192

        for buf in u.iter_content(block_sz):
            if buf:
                f.write(buf)
                file_size_dl += len(buf)
                dlbar.update(file_size_dl)
        dlbar.finish()
        sys.stdout.flush()
        f.close()

        try:
            meta = EasyID3(tempfile_name)
        except mutagen.id3.ID3NoHeaderError:
            meta = mutagen.mp3.EasyMP3(tempfile_name)
            meta.add_tags()

        meta['title'] = track['title']
        meta['artist'] = track['user']['username']
        meta['genre'] = track['genre']
        meta.save()

        os.rename(tempfile_name, track['filename'])


def main(args):
    print('SoundCloud Page Downloader By J. Merriman and C. Johnson\n'
          'http://chainsawpolice.github.io/ http://calebj.io/\n')

    if not args.u:
        print('\nPlease enter The user\'s SoundCloud permalink\n'
              '(a.k.a The link to their profile, without the "http://soundcloud.com" at the start).\n'
              'e.g. chainsawpolice, diplo, skrillex, etc.\n')
        username = input('> ')
    else:
        username = args.u

    tracks_url = resolve_profile_tracks_url(username)

    print('Downloading tracks for ' + username)
    directory = os.path.join('soundcloud-downloads', username)
    if not os.path.exists(directory):
        os.makedirs(directory)

    tracks_num = int(get_profile_info(username)['track_count'])
    if tracks_num > 200:
        track_listing = get_profile_tracks_pbar(tracks_url, tracks_num)
    else:
        track_listing = get_profile_tracks(tracks_url)
    download_tracks(track_listing, directory)

    if platform.system() == 'Windows':
        input('Press enter to continue...')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Download a SoundCloud user\'s music. All of it.')
    parser.add_argument(
        '-u', help='The user\'s SoundCloud permalink (a.k.a The link to their profile, without the "http://soundcloud.com" at the start)')
    parsed_args = parser.parse_args()
    main(parsed_args)
