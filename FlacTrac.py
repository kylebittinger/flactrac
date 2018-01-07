#!/usr/bin/env python
import copy
import fnmatch
import mutagen.flac
import mutagen.easyid3
import optparse
import os
import shutil
import subprocess
import sys
import tempfile

def maybe_mkdir(dir_path):
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)

def match_ext(filename, ext):
    _, observed_ext = os.path.splitext(filename)
    lowercase_ext = observed_ext.lower()
    return lowercase_ext == ext

def replace_ext(filename, new_ext):
    basename, _ = os.path.splitext(filename)
    return basename + new_ext

class Converter(object):
    def __init__(self, export_dir, bitrate, use_fixed_bitrate):
        self.export_dir = export_dir
        self.bitrate = bitrate
        self.use_fixed_bitrate = use_fixed_bitrate

    def convert_directory(self, input_dir):
        output_dir = self.init_output_dir(input_dir)
        flac_fps = self.get_track_filepaths(input_dir, ".flac")
        if flac_fps:
            sys.stderr.write("Converting FLAC files in %s\n" % input_dir)
            temp_dir = tempfile.mkdtemp()
            for flac_fp in flac_fps:
                wav_fp = self.flac_to_wav(flac_fp, temp_dir)
                converted_fp = self.get_converted_fp(wav_fp, output_dir)
                self.convert_wav(wav_fp, converted_fp)
                tags = self.get_flac_tags(flac_fp)
                self.set_converted_tags(converted_fp, tags)
            shutil.rmtree(temp_dir)
            return None
        else:
            wav_fps = self.get_track_filepaths(input_dir, ".wav")
            if wav_fps:
                sys.stderr.write("Converting WAV files in %s\n" % input_dir)
                for wav_fp in wav_fps:
                    converted_fp = self.get_converted_fp(wav_fp, output_dir)
                    self.convert_wav(wav_fp, converted_fp)
                return None
        sys.stderr.write("No FLAC or WAV files found in %s\n" % input_dir)

    def get_flac_tags(self, flac_fp):
        f = mutagen.flac.FLAC(flac_fp)
        tags = {}
        for key, val in f.tags:
            # standardize flac tags to all lowercase
            key = key.lower()
            tags[key] = val
        return tags

    def get_track_filepaths(self, input_dir, ext="flac"):
        track_filepaths = []
        for fname in os.listdir(input_dir):
            fpath = os.path.join(input_dir, fname)
            if os.path.isfile(fpath) and match_ext(fname, ext):
                track_filepaths.append(fpath)
        track_filepaths.sort()
        return track_filepaths

    def flac_to_wav(self, flac_filepath, output_dir):
        wav_filename = replace_ext(os.path.basename(flac_filepath), '.wav')
        wav_filepath = os.path.join(output_dir, wav_filename)

        args = ['flac', '-d', flac_filepath, '-o', wav_filepath]
        subprocess.check_call(args)
        return wav_filepath

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

    def get_converted_fp(self, wav_filepath, output_dir):
        converted_filename = replace_ext(
            os.path.basename(wav_filepath), self.output_ext)
        return os.path.join(output_dir, converted_filename)


class Mp3Converter(Converter):
    output_ext = '.mp3'

    def format_tracknumber_str(self, tags):
        n = tags['tracknumber']
        total = tags.get('tracktotal')
        if total:
            return '%s/%s' % (n, total)
        else:
            return '%s' % n

    def format_discnumber_str(self, tags):
        n = tags['discnumber']
        total = tags.get('disctotal')
        if total:
            return '%s/%s' % (n, total)
        else:
            return '%s' % n

    def set_converted_tags(self, converted_fp, tags):
        tags = copy.deepcopy(tags)
        f = mutagen.easyid3.EasyID3(converted_fp)
        id3_standard_tags = [
            'album', 'compilation', 'title', 'artist', 'date', 'genre',
            ]
        for tagname in id3_standard_tags:
            if tagname in tags:
                f[tagname] = tags[tagname]
        if 'tracknumber' in tags:
            f['tracknumber'] = self.format_tracknumber_str(tags)
        if 'discnumber' in tags:
            f['discnumber'] = self.format_discnumber_str(tags)
        # TODO: Fix multiple-choice genre tag
        f.save()

    def convert_wav(self, wav_filepath, converted_filepath):
        if self.use_fixed_bitrate:
            bitrate_args = ['-b', str(self.bitrate)]
        else:
            bitrate_args = ['-V', self.vbr_quality]
        args = ['lame', '--add-id3v2'] + bitrate_args + \
            [wav_filepath, converted_filepath]
        retcode = subprocess.check_call(args)
        return True

    def _get_vbr_quality(self):
        # Thresholds are at average of max bitrate for lower quality
        # setting and min bitrate for higher quality setting.  See
        # http://wiki.hydrogenaudio.org/index.php?title=LAME
        if self.bitrate < 145: # max_5 = 150, min_4 = 140
            return '5'
        elif self.bitrate < 167.5: # max_4 = 185, min_3 = 150
            return '4'
        elif self.bitrate < 182.5: # max_3 = 195, min_2 = 170
            return '3'
        elif self.bitrate < 200: # max_2 = 210, min_1 = 190
            return '2'
        elif self.bitrate < 235: # max_1 = 250, min_0 = 220
            return '1'
        else:
            return '0'
    vbr_quality = property(_get_vbr_quality)

class FlacTracApp(object):
    converter_classes = {
        'mp3': Mp3Converter,
        }

    def __init__(self, args=None):
        parser = self._build_parser()
        opts, args = parser.parse_args(args)
        self.flac_dirs = [os.path.realpath(d) for d in args]
        output_dir = os.path.expanduser(opts.output_dir)
        maybe_mkdir(output_dir)
        try:
            converter_class = self.converter_classes[opts.format]
        except KeyError:
            parser.error('Unknown output format: %s' % opts.format)
        self.converter = converter_class(
            output_dir, opts.bitrate, opts.use_fixed_bitrate)

    def _build_parser(self):
        p = optparse.OptionParser(usage='%prog [options] flac_dir')
        p.add_option('-f', '--format', default='mp3',
            help='output file format. Choices: ' + \
                ', '.join(self.converter_classes.keys()) + \
                '. [default: %default]')
        p.add_option('-b', '--bitrate', type='int', default=320,
            help='bitrate of output files [default: 320 kbps]')
        p.add_option('--use_fixed_bitrate', action='store_true', default=False,
            help='use fixed bitrate encoding [default: %default]')
        p.add_option('-o', '--output_dir', default='~/Desktop/Export',
            help='output directory [default: %default]')
        return p

    def run(self):
        for flac_dir in self.flac_dirs:
            self.converter.convert_directory(flac_dir)

if __name__ == '__main__':
    FlacTracApp().run()
