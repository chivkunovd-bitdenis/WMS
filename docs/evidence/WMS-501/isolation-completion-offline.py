"""Prevent tests from opening any network connection outside audit loopback."""
import os,socket
assert os.environ.get('WMS_TEST_DATABASE_URL') == 'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_isolation2'
_connect=socket.socket.connect
_connect_ex=socket.socket.connect_ex

def checked(address):
    if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
        raise RuntimeError('WMS501_OFFLINE: external network blocked')
def connect(self,address):
    checked(address); return _connect(self,address)
def connect_ex(self,address):
    checked(address); return _connect_ex(self,address)
def pytest_configure(config):
    socket.socket.connect=connect
    socket.socket.connect_ex=connect_ex
