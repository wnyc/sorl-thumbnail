import os

from django.conf import settings
from django.core.cache import get_cache
from django.utils.encoding import iri_to_uri, force_unicode
from django.core.files.storage import DefaultStorage
from django.core.files import File
from hashlib import md5 
from sorl.thumbnail.base import Thumbnail
from sorl.thumbnail.processors import dynamic_import
from sorl.thumbnail import defaults
from StringIO import StringIO 
from tempfile import NamedTemporaryFile

cache = get_cache('default')

def get_thumbnail_setting(setting, override=None):
    """
    Get a thumbnail setting from Django settings module, falling back to the
    default.

    If override is not None, it will be used instead of the setting.
    """
    if override is not None:
        return override
    if hasattr(settings, 'THUMBNAIL_%s' % setting):
        return getattr(settings, 'THUMBNAIL_%s' % setting)
    else:
        return getattr(defaults, setting)


def build_thumbnail_name(source_name, size, options=None,
                         quality=None, basedir=None, subdir=None, prefix=None,
                         extension=None):
    quality = get_thumbnail_setting('QUALITY', quality)
    basedir = get_thumbnail_setting('BASEDIR', basedir)
    subdir = get_thumbnail_setting('SUBDIR', subdir)
    prefix = get_thumbnail_setting('PREFIX', prefix)
    extension = get_thumbnail_setting('EXTENSION', extension)
    path, filename = os.path.split(source_name)
    basename, ext = os.path.splitext(filename)
    name = '%s%s' % (basename, ext.replace(os.extsep, '_'))
    size = '%sx%s' % tuple(size)

    # Handle old list format for opts.
    options = options or {}
    if isinstance(options, (list, tuple)):
        options = dict([(opt, None) for opt in options])

    opts = options.items()
    opts.sort()   # options are sorted so the filename is consistent
    opts = ['%s_' % (v is not None and '%s-%s' % (k, v) or k)
            for k, v in opts]
    opts = ''.join(opts)
    extension = extension and '.%s' % extension
    thumbnail_filename = '%s%s_%s_%sq%s%s' % (prefix, name, size, opts,
                                              quality, extension)
    return os.path.join(basedir, path, subdir, thumbnail_filename)


class DjangoThumbnail(Thumbnail):
    imagemagick_file_types = get_thumbnail_setting('IMAGEMAGICK_FILE_TYPES')

    def __init__(self, relative_source, requested_size, opts=None,
                 quality=None, basedir=None, subdir=None, prefix=None,
                 relative_dest=None, processors=None, extension=None, storage_server=None):
        if not storage_server:
            storage_server = DefaultStorage()
        relative_source = force_unicode(relative_source)
        # Set the absolute filename for the source file
        with self._get_data_as_tempfile(relative_source, storage_server) as source:

            quality = get_thumbnail_setting('QUALITY', quality)
            convert_path = get_thumbnail_setting('CONVERT')
            wvps_path = get_thumbnail_setting('WVPS')
            if processors is None:
                processors = dynamic_import(get_thumbnail_setting('PROCESSORS'))

            # Call super().__init__ now to set the opts attribute. generate() won't
            # get called because we are not setting the dest attribute yet.
            super(DjangoThumbnail, self).__init__(source, requested_size,
                opts=opts, quality=quality, convert_path=convert_path,
                wvps_path=wvps_path, processors=processors)

            # Get the relative filename for the thumbnail image, then set the
            # destination filename
            if relative_dest is None:
                relative_dest = \
                   self._get_relative_thumbnail(relative_source.name, basedir=basedir,
                                                subdir=subdir, prefix=prefix,
                                                extension=extension)
            
            with NamedTemporaryFile() as dest:
                self.dest = dest.name
                
                self.generate()
                dest.seek(0)
                data = dest.read()
                f = StringIO(data)
                f.name = relative_dest
                f.size = len(data)
                self.relative_url = storage_server.save(relative_dest, File(f))
                self.absolute_url = os.path.join(settings.MEDIA_URL, self.relative_url)


    def _get_relative_thumbnail(self, relative_source,
                                basedir=None, subdir=None, prefix=None,
                                extension=None):
        """
        Returns the thumbnail filename including relative path.
        """
        return build_thumbnail_name(relative_source, self.requested_size,
                                    self.opts, self.quality, basedir, subdir,
                                    prefix, extension)

    # Was _absolute_path
    def _get_data_as_tempfile(self, filename, storage_server):
        key = 'sorl:' + md5(filename).hexdigest()
        data = cache.get(key)
        if data is None:
            data = storage_server.open(filename).read()
            cache.set(key, data)
        f = NamedTemporaryFile()
        f.write(data)
        f.seek(0)
        return f 


    def __unicode__(self):
        return self.absolute_url
