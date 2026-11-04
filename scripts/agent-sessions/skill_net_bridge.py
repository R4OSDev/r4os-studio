"""Private namespace loopback to its one mounted public-web proxy socket."""
import asyncio
import os
import sys


async def connection(reader,writer):
    remote=None
    try:
        source,remote=await asyncio.open_unix_connection('/runner/egress.sock')
        async def pump(a,b):
            while block:=await a.read(65536):b.write(block);await b.drain()
            if b.can_write_eof():b.write_eof()
        tasks=[asyncio.create_task(pump(reader,remote)),asyncio.create_task(pump(source,writer))]
        try:await asyncio.gather(*tasks)
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    except (OSError,ConnectionError):pass
    finally:
        for stream in (remote,writer):
            if stream:
                stream.close()
                try:await stream.wait_closed()
                except (OSError,ConnectionError):pass


async def main():
    server=await asyncio.start_server(connection,'127.0.0.1',3128)
    fd=int(sys.argv[1]);os.write(fd,b'ready');os.close(fd)
    async with server:await server.serve_forever()


if __name__=='__main__':asyncio.run(main())
