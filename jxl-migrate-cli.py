#!/usr/bin/env python
from threading import Semaphore

version = 'v0.3.3'

'''
jxl-migrate - Convert images to JPEG XL (JXL) format
Copyright (C) 2021-present Kyle Alexander Buan

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''

import os, sys
import subprocess
import time
import tempfile
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
from subprocess import check_output

filesize_before_conversion = 0
filesize_after_conversion = 0

arguments = {}


def is_webp_lossless(p):
    output = check_output(args=[
        'webpinfo',
        p
    ], text=True)

    return 'Format: Lossless' in output


def convert(p, target_filename, lossy=False, remove=False, losslessjpeg=False):
    proc = subprocess.run(args=[
                                   'cjxl',
                                   p,
                                   target_filename,
                                   '-d',
                                   '1' if lossy else '0',
                                   '-j',
                                   '1' if losslessjpeg else '0'
                               ] + arguments['cjxl_extra_args'], capture_output=True)

    if proc.returncode != 0 or not os.path.exists(target_filename):
        return None
    else:
        os.utime(target_filename, (time.time(), os.path.getmtime(p)))
        if remove:
            os.remove(p)
        return target_filename


def convert_webp_to_temporary_png(webp_filename):
    temporary_png_filename = tempfile.NamedTemporaryFile(prefix='jxl-migrate-cli-', suffix='.png').name

    print_thread_safe("Converting " + webp_filename + " to a temporary PNG " + temporary_png_filename)

    proc = subprocess.run(args=[
        'dwebp',
        webp_filename,
        '-o',
        temporary_png_filename
    ], capture_output=True)

    if proc.returncode != 0 or not os.path.exists(temporary_png_filename):
        return None
    else:
        os.utime(temporary_png_filename, (time.time(), os.path.getmtime(webp_filename)))
        return temporary_png_filename

def convert_bmp_to_temporary_png(bmp_filename):
    temporary_png_filename = tempfile.NamedTemporaryFile(prefix='jxl-migrate-cli-', suffix='.png').name

    print_thread_safe("Converting " + bmp_filename + " to a temporary PNG " + temporary_png_filename)

    proc = subprocess.run(args=[
        'magick',
        bmp_filename,
        temporary_png_filename
    ], capture_output=True)

    if proc.returncode != 0 or not os.path.exists(temporary_png_filename):
        return None
    else:
        os.utime(temporary_png_filename, (time.time(), os.path.getmtime(bmp_filename)))
        return temporary_png_filename


def handle_file(filename, root):
    global filesize_before_conversion
    global filesize_after_conversion
    global arguments

    extension = filename.split('.')[-1].lower()

    fullpath = os.path.join(root, filename)
    filesize = os.path.getsize(fullpath)
    if filesize == 0:
        print_thread_safe('Skipping zero-byte file ' + fullpath)
        return
    lossy = False
    losslessjpeg = False
    decoded_png_filename = None

    supported_extensions = ['jpg', 'jpeg', 'gif', 'png', 'apng', 'webp', 'bmp']

    if extension not in supported_extensions:
        if extension != 'jxl':
            print_thread_safe('Not supported: ' + fullpath)
        return

    if extension in arguments['ignore_extensions']:
        print_thread_safe('Ignoring ' + fullpath)
        return

    filename_without_extension = '.'.join(filename.split('.')[:-1])
    jxl_filename = os.path.join(root, filename_without_extension) + '.jxl'
    if not arguments['force_overwrite']:
        if os.path.exists(jxl_filename):
            print_thread_safe(jxl_filename + ' already exists, skipping ' + filename)
            return
    if extension in ['jpg', 'jpeg']:
        lossy = arguments['lossyjpg']
        losslessjpeg = not arguments['lossyjpg']
    elif extension in ['gif']:
        lossy = arguments['lossygif']
    elif extension in ['png']:
        lossy = arguments['lossypng']
    elif extension in ['bmp']:
        decoded_png_filename = convert_bmp_to_temporary_png(fullpath)
        if decoded_png_filename is None:
            return
        if arguments['lossybmp']:
            lossy = True
        fullpath = decoded_png_filename
    elif extension in ['webp']:
        decoded_png_filename = convert_webp_to_temporary_png(fullpath)
        if decoded_png_filename is None:
            return
        if arguments['lossywebp']:
            lossy = True
        else:
            lossy = not is_webp_lossless(fullpath)
        fullpath = decoded_png_filename
    message = "Converting " + fullpath + " to "
    if lossy:
        message += "a lossy"
    elif losslessjpeg:
        message += "a recompressed reversible"
    else:
        message += "a lossless"
    message += " JXL"
    print_thread_safe(message)

    converted_filename = convert(fullpath, jxl_filename, lossy, arguments['delete'], losslessjpeg)
    if converted_filename is None:
        print_thread_safe('Conversion FAILED: ' + fullpath)
    else:
        filesize_before_conversion += filesize
        filesize_after_conversion += os.path.getsize(converted_filename)

    if decoded_png_filename is not None:
        os.remove(decoded_png_filename)


def try_handle_file(filename, root):
    try:
        handle_file(filename, root)
    except Exception as inst:
        print_thread_safe('Error processing ' + os.path.join(root, filename) + ': ', repr(inst))


def format_file_size(size_in_bytes):
    for unit in ['Bytes', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.3f} {unit}"
        size_in_bytes /= 1024.0


print_lock = Semaphore(value=1)


def print_thread_safe(*args, sep=' ', end='\n', file=None):
    with print_lock:
        print(*args, sep=sep, end=end, file=file)


def run():
    global arguments

    if len(sys.argv) <= 1:
        print_help()

    arguments = {
        'delete': False,
        'lossyjpg': False,
        'lossywebp': False,
        'lossypng': False,
        'lossybmp': False,
        'lossygif': False,
        'force_overwrite': False,
        'source': None,
        'ignore_extensions': [],
        'cjxl_extra_args': [],
        'jobs': cpu_count(),
    }

    for i, arg in enumerate(sys.argv[1:]):
        if arg == '-h' or arg == '--help':
            print_help()
        elif arg == '-v' or arg =='-V' or arg == '--v' or arg == '--version':
            print_version()
        if arg.startswith('--'):
            if arg == '--delete':
                arguments['delete'] = True
            elif arg == '--lossyjpg':
                arguments['lossyjpg'] = True
            elif arg == '--lossywebp':
                arguments['lossywebp'] = True
            elif arg == '--lossygif':
                arguments['lossygif'] = True
            elif arg == '--lossypng':
                arguments['lossypng'] = True
            elif arg == '--lossybmp':
                arguments['lossybmp'] = True
            elif arg == '--force-overwrite':
                arguments['force_overwrite'] = True
            elif arg.startswith('--jobs='):
                try:
                    arguments['jobs'] = int(arg.split('=')[1])
                except ValueError:
                    print('Invalid value for --jobs. Must be an integer.')
                    exit(1)
                if arguments['jobs'] < 1:
                    print('Invalid value for --jobs. Must be greater than 0.')
                    exit(1)
            elif arg.startswith('--cjxl-extra-args='):
                arguments['cjxl_extra_args'] = arg.split('=')[1].split(' ')
            elif arg.startswith('--ignore-formats='):
                arguments['ignore_extensions'] = arg.split('=')[1].split(',')
            else:
                print('Unrecognized flag: ' + arg)
                exit(1)
        else:
            if arguments['source'] is not None:
                print(f'Multiple arguments that can be interpreted as a source directory found: '
                      f'"{arguments["source"]}", "{arg}".')
                exit(1)
            arguments['source'] = arg

    source_directory = arguments['source']
    if source_directory is None:
        print('Missing directory to process.')
        exit(1)

    if not os.access(source_directory, os.W_OK | os.X_OK | os.R_OK):
        print(f'Failed to open directory "{source_directory}" for reading and writing')
        exit(1)

    pool = ThreadPool(arguments['jobs'])
    for root, subdirs, files in os.walk(arguments['source']):
        for filename in files:
            pool.apply_async(try_handle_file, (filename, root))
    pool.close()
    pool.join()

    if filesize_before_conversion == 0:
        print('No files were converted')
        exit()
    print('Before conversion: ' + format_file_size(filesize_before_conversion))
    print('After conversion: ' + format_file_size(filesize_after_conversion))
    reduction_percentage = (1 - filesize_after_conversion / filesize_before_conversion) * 100

    print(f"Reduction: {reduction_percentage:.2f}%")


def print_version():
    global version
    print(version)
    exit()


def print_help():
    global version
    print(f'jxl-migrate-cli {version} - Convert images in a directory to JPEG XL (JXL) format\n')
    print('Program usage:')
    print(sys.argv[0] + ' [directory] [OPTIONS]\n')
    print('directory: the folder to process\n')
    print('--help: print this message and exit')
    print('--version: print version and exit')
    print('--delete: delete original source files if conversion succeeded (default FALSE)')
    print('--lossyjpg: convert JPEG files lossily (-d 1) (default FALSE)')
    print('--lossywebp: convert lossless WebP lossily (-d 1) (default FALSE)')
    print('--lossygif: convert GIF lossily (-d 1) (default FALSE)')
    print('--lossypng: convert PNG lossily (-d 1) (default FALSE)')
    print('--lossybmp: convert BMP lossily (-d 1) (default FALSE)')
    print('--force-overwrite: perform conversion even if JXL file already exists')
    print('--ignore-formats: comma-separated list of file extensions to ignore, e.g. --ignore-formats=jpg,png')
    print('--jobs: number of jobs (cjxl processes) to use (defaults to CPU core count), e.g. --jobs=8')
    print('--cjxl-extra-args: Additional parameters to pass to jxl, e.g. --cjxl-extra-args="-e 8" to set cjxl '
          'effort to 8')
    exit()


if __name__ == '__main__':
    run()
