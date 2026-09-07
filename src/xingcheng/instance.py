"""One owner per data directory, with OS-released locks after a crash."""

import os
from pathlib import Path

from .localstore import LocalError


class InstanceLock:
    def __init__(self, root):
        Path(root).mkdir(parents=True, exist_ok=True)
        self.stream = (Path(root) / "application.lock").open("a+b")
        self.stream.seek(0, 2)
        if not self.stream.tell():
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise LocalError(
                "ALREADY_RUNNING",
                "此数据目录已被 CaliSift 使用，请关闭已有窗口或命令行任务后重试",
            ) from exc

    def close(self):
        if not self.stream.closed:
            self.stream.close()
