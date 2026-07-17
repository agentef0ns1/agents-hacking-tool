"""Inspección de permisos POSIX."""

from __future__ import annotations

import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PathPermission:
    path: str
    exists: bool
    mode: str | None
    owner_uid: int | None
    owner_gid: int | None
    readable: bool | None
    writable: bool | None
    executable: bool | None
    is_symlink: bool | None
    symlink_target: str | None
    file_type: str | None = None


def mode_to_octal(mode: int) -> str:
    return oct(stat.S_IMODE(mode))[-3:]


def file_type_label(path: Path, st_mode: int) -> str:
    if path.is_symlink():
        return "symlink"
    if stat.S_ISDIR(st_mode):
        return "directory"
    if stat.S_ISREG(st_mode):
        return "file"
    if stat.S_ISFIFO(st_mode):
        return "fifo"
    if stat.S_ISSOCK(st_mode):
        return "socket"
    return "other"


def inspect_permissions(path: Path) -> PathPermission:
    if not path.exists() and not path.is_symlink():
        return PathPermission(
            path=str(path),
            exists=False,
            mode=None,
            owner_uid=None,
            owner_gid=None,
            readable=None,
            writable=None,
            executable=None,
            is_symlink=None,
            symlink_target=None,
            file_type=None,
        )

    st = path.lstat()
    target = None
    is_symlink = path.is_symlink()
    if is_symlink:
        try:
            target = str(path.readlink())
        except OSError:
            target = "<unreadable>"

    return PathPermission(
        path=str(path),
        exists=True,
        mode=mode_to_octal(st.st_mode),
        owner_uid=st.st_uid,
        owner_gid=st.st_gid,
        readable=os.access(path, os.R_OK),
        writable=os.access(path, os.W_OK),
        executable=os.access(path, os.X_OK),
        is_symlink=is_symlink,
        symlink_target=target,
        file_type=file_type_label(path, st.st_mode),
    )


def inspect_tree(root: Path, *, max_depth: int | None = None) -> list[PathPermission]:
    results: list[PathPermission] = []
    if not root.exists():
        return [inspect_permissions(root)]

    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        if max_depth is not None and len(current.parts) - root_depth > max_depth:
            dirnames.clear()
            continue

        results.append(inspect_permissions(current))
        for name in sorted(filenames):
            results.append(inspect_permissions(current / name))

    return results


def permission_dict(path: Path) -> dict:
    return asdict(inspect_permissions(path))
