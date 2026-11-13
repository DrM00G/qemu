"""Deterministic local TCP/UDP echo endpoints, payload evidence remains in lab."""
import json
import socket
import threading
import time

class Endpoints:
    def __init__(self, path):
        self.trace=open(path,'w');self.lock=threading.Lock();self.sockets=[]
        self.ports={}
        for kind,name in [(socket.SOCK_STREAM,'tcp'),(socket.SOCK_DGRAM,'udp')]:
            s=socket.socket(socket.AF_INET,kind);s.bind(('127.0.0.1',0));s.settimeout(.5)
            if kind==socket.SOCK_STREAM:s.listen(4)
            self.sockets.append(s);self.ports[name]=s.getsockname()[1]
            threading.Thread(target=self.loop,args=(s,name),daemon=True).start()
    def loop(self,s,name):
        while True:
            try:
                if name=='tcp':
                    c,_=s.accept();c.settimeout(2)
                    with c:
                        b=c.recv(4096);c.sendall(b)
                else:
                    b,peer=s.recvfrom(4096);s.sendto(b,peer)
                with self.lock:
                    self.trace.write(json.dumps(dict(protocol=name,tx=b.hex(),rx=b.hex(),
                                                     monotonic=time.monotonic()))+'\n');self.trace.flush()
            except socket.timeout:continue
            except OSError:break
