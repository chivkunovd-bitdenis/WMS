"""Read selected ZIP members with HTTP ranges; never download the whole artifact."""
import io
import json
import pathlib
import subprocess
import sys
import urllib.request
import zipfile

artifact, destination, *wanted = sys.argv[1:]
token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
req = urllib.request.Request(
    f'https://api.github.com/repos/chivkunovd-bitdenis/WMS/actions/artifacts/{artifact}/zip',
    headers={'Authorization': f'Bearer {token}'})
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None
try:
    urllib.request.build_opener(NoRedirect).open(req)
except urllib.error.HTTPError as error:
    if error.code != 302:
        raise
    url = error.headers['Location']
del token
size = int(urllib.request.urlopen(urllib.request.Request(url, method='HEAD')).headers['Content-Length'])
class RemoteZip(io.RawIOBase):
    position = 0
    transferred = 0
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else size + offset
        return self.position
    def read(self, count=-1):
        count = size - self.position if count < 0 else min(count, size - self.position)
        if count <= 0: return b''
        request = urllib.request.Request(url, headers={'Range': f'bytes={self.position}-{self.position+count-1}'})
        with urllib.request.urlopen(request) as response:
            if response.status != 206: raise RuntimeError('Server did not honor selective range request')
            data = response.read()
        self.position += len(data)
        self.transferred += len(data)
        return data
remote = RemoteZip()
with zipfile.ZipFile(remote) as archive:
    names = archive.namelist()
    if not wanted:
        print(json.dumps(names, ensure_ascii=False, indent=2))
    else:
        root = pathlib.Path(destination)
        root.mkdir(parents=True, exist_ok=True)
        for name in wanted:
            if name not in names: raise RuntimeError(f'Missing member: {name}')
            target = root / pathlib.Path(name).name
            target.write_bytes(archive.read(name))
            print(f'{name} -> {target}')
print(f'Range bytes received: {remote.transferred}; archive size: {size}')
