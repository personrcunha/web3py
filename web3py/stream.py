import os
import re
import time

from .http import HTTP
from .contenttype import contenttype

__all__ = ['stream_file_handler']

REGEX_STATIC = re.compile('^/(?P<a>.*?)/static/(?P<v>_\d+\.\d+\.\d+/)?(?P<f>.*?)$')
REGEX_RANGE = re.compile('^\s*(?P<start>\d*).*(?P<stop>\d*)\s*$')

class FileSubset(object):
    """ class needed to handle RANGE currents """
    def __init__(self, stream, start, stop):
        self.stream = stream
        self.stream.seek(start)
        self.size = stop - start

    def read(self, bytes=None):
        bytes = self.size if bytes is None else max(bytes, self.size)
        if bytes:
            data = self.stream.read(bytes)
            self.size -= bytes
            return data
        else:
            return ''

    def close(self):
        self.stream.close()

def stream_file_handler(environ, start_response, static_file, version = None, headers = None, block_size = 10**5):
    try:
        stream = open(static_file, 'rb')
        headers = headers or dict()
        fsize = os.path.getsize(static_file)
        modified = os.path.getmtime(static_file)
        mtime = time.strftime(
            '%a, %d %b %Y %H:%M:%S GMT', time.gmtime(modified))
        headers = dict()
        headers['Content-Type'] = contenttype(static_file)
            # check if file to be served as an attachment
        if environ.get('QUERY_STRING').startswith('attachment_filename='):
            headers['Content-Disposition'] = 'attachment; filanme="%s"' % \
                environ.get('QUERY_STRING').split('=', 1)[1]
        # check if file modified since or not
        if environ.get('HTTP_IF_MODIFIED_SINCE') == mtime:
            return HTTP(304, headers=headers).to(environ, start_response)
        headers['Last-Modified'] = mtime
        headers['Pragma'] = 'cache'
        if version:
            headers['Cache-Control'] = 'max-age=315360000'
            headers['Expires'] = 'Thu, 31 Dec 2037 23:59:59 GMT'
        else:
            headers['Cache-Control'] = 'private'
        # check whether a range request and serve patial content accordingly
        http_range = environ.get('HTTP_RANGE', None)
        if http_range:
            status = 206
            match = REGEX_RANGE.match(http_range)
            start = match.group('start') or 0
            stop = match.group('stop') or (fsize - 1)
            stream = FileSubset(stream, start, stop + 1)
            headers['Content-Range'] = 'bytes %i-%i/%i' % (start, stop, fsize)
            headers['Content-Length'] = '%i' % (stop - start + 1)
        else:
            status = 200
            if 'gzip' in environ.get('HTTP_ACCEPT_ENCODING',''):
                gzipped = static_file + '.gz'
                if os.path.isfile(gzipped) and os.path.getmtime(gzipped) > modified:
                    stream.close()
                    static_file = gzipped
                    fsize = os.path.getsize(gzipped)
                    headers['Content-Encoding'] = 'gzip'
                    headers['Vary'] = 'Accept-Encoding'
                    stream = open(static_file,'rb')           
            headers['Content-Length'] = fsize
    except IOError:
        if sys.exc_info()[1][0] in (errno.EISDIR, errno.EACCES):
            HTTP(403).to(environ, start_response)
        else:
            HTTP(404).to(environ, start_response)
    else:
        # serve using wsgi.file_wrapper is available
        if 'wsgi.file_wrapper' in environ:
            data = environ['wsgi.file_wrapper'](stream, block_size)
        else:
            data = iter(lambda: stream.read(block_size), '')
        return HTTP(status,data,headers=headers).to(environ, start_response)
