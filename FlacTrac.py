#!/usr/bin/env python
import copy
import fnmatch
import mutagen.flac
import optparse
import os
import shutil
import subprocess
import tempfile

def maybe_mkdir(dir_path):
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)

def is_flac(filename):
    return fnmatch.fnmatch(filename, '*.flac')

def replace_ext(filename, new_ext):
    basename, _ = os.path.splitext(filename)
    return basename + new_ext

def ApplicationError(Exception): pass

class AacConverter(object):
    def __init__(self, export_dir, bitrate):
        self.bitrate = bitrate
        self.export_dir = export_dir

    def convert_directory(self, input_dir):
        output_dir = self.init_output_dir(input_dir)
        temp_dir = tempfile.mkdtemp()
        for flac_fp in self.get_flac_filepaths(input_dir):
            wav_fp = self.flac_to_wav(flac_fp, temp_dir)
            aac_fp = self.wav_to_aac(wav_fp, output_dir)
            tags = self.get_flac_tags(flac_fp)
            self.set_aac_tags(aac_fp, tags)
        shutil.rmtree(temp_dir)

    def get_flac_tags(self, flac_fp):
        f = mutagen.flac.FLAC(flac_fp)
        tags = {}
        for key, val in f.tags:
            # standardize flac tags to all lowercase
            key = key.lower()
            tags[key] = val
        return tags

    def set_aac_tags(self, aac_fp, tags):
        tags = copy.deepcopy(tags)
        # Change tag names to match nero options
        nero_tagnames = {
            'tracknumber': 'track', 'tracktotal': 'totaltracks',
            'discnumber': 'disc', 'disctotal': 'totaldiscs',
            'date': 'year',
            }
        for flac_tagname, nero_tagname in nero_tagnames.items():
            if flac_tagname in tags:
                val = tags[flac_tagname]
                del tags[flac_tagname]
                tags[nero_tagname] = val
        # Filter, keeping only standard tags
        nero_standard_tags = [
            'title', 'artist', 'year', 'album', 'genre', 'track', 'totaltracks', 
            'disc', 'totaldiscs', 'url', 'copyright', 'comment', 'lyrics', 
            'credits', 'rating', 'label', 'composer', 'isrc', 'mood', 'tempo',
            ]
        for tagname in tags.keys():
            if tagname not in nero_standard_tags:
                print "Tag %s not in standard fields, skipping." % tagname
                del tags[tagname]
        nero_opts = ['-meta:%s=%s' % x for x in tags.items()]
        nero_args = ['neroAacTag', aac_fp] + nero_opts
        return subprocess.check_call(nero_args)

    def get_flac_filepaths(self, input_dir):
        flac_filepaths = []
        for subdir, dirnames, filenames in os.walk(input_dir):
            # Only search top-level directory
            del dirnames[:]
            flac_filepaths.extend([
                    os.path.join(input_dir, subdir, fn) for fn in 
                    filter(is_flac, filenames)])
        flac_filepaths.sort()
        return flac_filepaths

    def flac_to_wav(self, flac_filepath, output_dir):
        wav_filename = replace_ext(os.path.basename(flac_filepath), '.wav')
        wav_filepath = os.path.join(output_dir, wav_filename)

        args = ['flac', '-d', flac_filepath, '-o', wav_filepath]
        retcode = subprocess.call(args)
        if retcode != 0:
            raise ApplicationError('Nonzero return code from process %s' % args)
        return wav_filepath

    def wav_to_aac(self, wav_filepath, output_dir):
        aac_filename = replace_ext(os.path.basename(wav_filepath), '.m4a')
        aac_filepath = os.path.join(output_dir, aac_filename)

        # Nero encoder uses bit/s instead of kbit/s
        nero_bitrate = self.bitrate * 1000
        args = map(str, [
                'neroAacEnc', 
                # '-2pass', 
                '-if', wav_filepath, 
                '-of', aac_filepath, 
                '-br', nero_bitrate
                ])
        retcode = subprocess.call(args)
        if retcode != 0:
            raise ApplicationError('Nonzero return code from process %s' % args)
        return aac_filepath

    def init_output_dir(self, input_dir):
        """Initialize subdirectory structure in output_dir
        
        Assumes that input directory has structure
        /music/folder/Artist/Album
        and creates the Artist/Album folders in output_dir.
        """
        input_dir = os.path.realpath(input_dir)
        parent_dir, album_dirname = os.path.split(input_dir)
        _, artist_dirname = os.path.split(parent_dir)

        output_artist_dir = os.path.join(
            self.export_dir, artist_dirname)
        maybe_mkdir(output_artist_dir)
        
        output_album_dir = os.path.join(
            output_artist_dir, album_dirname)
        maybe_mkdir(output_album_dir)
        return output_album_dir


class FlacTracApp(object):
    def __init__(self, args=None):
        parser = self._build_parser()
        opts, self.flac_dirs = parser.parse_args(args)
        maybe_mkdir(opts.output_dir)
        self.converter = AacConverter(opts.output_dir, opts.bitrate)

    def _build_parser(self):
        p = optparse.OptionParser()
        p.add_option('-b', '--bitrate', type='int', default=160,
            help='bitrate of output files [default: %default]')
        p.add_option('-o', '--output_dir', default='/home/kyle/Desktop/Export',
            help='output directory [default: %default]')
        return p

    def run(self):
        for flac_dir in self.flac_dirs:
            self.converter.convert_directory(flac_dir)

if __name__ == '__main__':
    FlacTracApp().run()
