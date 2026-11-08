"""Bounded cleanup of an original terminal session, using identity-bound signals."""
import asyncio
import os
from pathlib import Path
import signal


def identity(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        return fields[0], int(fields[2]), int(fields[3]), int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


class Group:
    def __init__(self, pid, birth):
        self.pid = pid
        self.birth = int(birth) if birth is not None else None
        self.empty = False

    def members(self):
        if self.empty: return []
        leader = identity(self.pid)
        if leader and (self.birth is None or leader[3] != self.birth):
            return None  # Never follow a reused leader identity.
        members = []
        for entry in Path('/proc').iterdir():
            if not entry.name.isdecimal(): continue
            value = identity(int(entry.name))
            if value and value[0] not in ('Z', 'X') and value[1:3] == (self.pid, self.pid):
                if self.birth is None or value[3] < self.birth: return None
                members.append((int(entry.name), value))
        self.empty = not members
        return members

    def send(self, members, sig):
        for pid, original in members:
            try:
                fd = os.pidfd_open(pid)
                try:
                    current = identity(pid)
                    if current and current[1:] == original[1:]: signal.pidfd_send_signal(fd, sig)
                finally: os.close(fd)
            except ProcessLookupError: pass

    async def stop(self):
        for sig, seconds in ((signal.SIGTERM, 2), (signal.SIGKILL, 1)):
            deadline = asyncio.get_running_loop().time() + seconds
            sent = set()
            while True:
                members = self.members()
                if members is None: return False
                if not members: return True
                fresh = [(pid, value) for pid, value in members if (pid, value[3]) not in sent]
                self.send(fresh, sig)
                sent.update((pid, value[3]) for pid, value in fresh)
                if asyncio.get_running_loop().time() >= deadline: break
                await asyncio.sleep(.025)
        members = self.members()
        return members is not None and not members
