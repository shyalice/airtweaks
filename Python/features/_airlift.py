"""airlift primitives shared across features.

drives the streaming_zip_conduit + AirTrafficHost.framework ceremony to
read/write files inside sandboxed iOS paths (Carrier Bundles, CallHistoryDB,
anywhere reachable from /var/mobile/). no external binaries — all via
pymobiledevice3 + ctypes into apple's private framework on macOS.
"""
from __future__ import annotations
import asyncio
import ctypes as C
import hashlib
import io
import os
import platform
import plistlib
import re
import stat
import struct
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable


PAYLOAD_PATH = "q0/q1/q2/q3/q4/payload"
MAX_BYTES = 64 * 1024 * 1024
MAX_NODES = 4000

BOOK_FILES = ("Books/Books.plist", "Books/Sync/Books.plist",
              "Books/Sync/Upload.plist",
              "Books/Sync/Database/OutstandingAssets_4.sqlite",
              "Books/Sync/Database/OutstandingAssets_4.sqlite-shm",
              "Books/Sync/Database/OutstandingAssets_4.sqlite-wal")
BOOK_DIRS = ("Books", "Books/Sync", "Books/Sync/Database")


class OpError(RuntimeError):
    """domain failure — surface message to UI, no traceback."""


def require(ok, msg: str):
    if not ok:
        raise OpError(msg)


def _safe_component(name: str) -> None:
    require(isinstance(name, str) and 1 <= len(name) <= 255
            and not any(ord(c) < 32 for c in name)
            and name not in (".", ".."),
            f"unsafe path component: {name!r}")


def _safe_path(path: str) -> str:
    require(isinstance(path, str) and 1 <= len(path) <= 4096
            and not path.startswith("/") and not path.endswith("/"),
            f"unsafe path: {path!r}")
    for part in path.split("/"):
        _safe_component(part)
    return path


def _validate_tree(tree: dict) -> None:
    require(isinstance(tree, dict), "tree must be a dict")
    require(len(tree) <= MAX_NODES, f"tree exceeds {MAX_NODES} nodes")
    for name, (kind, value) in tree.items():
        _safe_path(name)
        require(kind in ("f", "l", "d"), f"unknown entry kind: {kind!r}")
        require(isinstance(value, bytes), f"entry value must be bytes: {name}")
        if kind == "f":
            require(len(value) <= MAX_BYTES, f"file too large: {name}")
        elif kind == "d":
            require(value == b"", f"dir value must be empty bytes: {name}")


def _zi(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (mode & 0xFFFF) << 16
    info.extra = struct.pack("<HHH", 0x5A53, 2, mode & 0xFFFF)
    return info


def _zip_entry_for(name: str, kind: str) -> zipfile.ZipInfo:
    mode = {"f": stat.S_IFREG | 0o644,
            "d": stat.S_IFDIR | 0o755,
            "l": stat.S_IFLNK | 0o777}[kind]
    zname = name + "/" if kind == "d" and not name.endswith("/") else name
    return _zi(zname, mode)


def _write_flat_tree_into_zip(z: zipfile.ZipFile, prefix: str, tree: dict) -> None:
    for name in sorted(tree):
        kind, value = tree[name]
        full = f"{prefix}/{name}" if prefix else name
        z.writestr(_zip_entry_for(full, kind), value)


def write_tree_zip(path: Path, tree: dict) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", allowZip64=False) as z:
        _write_flat_tree_into_zip(z, "", tree)
    path.write_bytes(buf.getvalue())


SYMLINK_SYSTEM_PREFIX = "../../../../../../System/Library/Carrier Bundles/iPhone/"


def _staging_archive(payload: dict | None, target: str) -> bytes:
    """build the airlift staging zip. escape-link points at target's PARENT
    (streaming_zip validates symlink targets → parent must be reachable via
    the relative chain from the placement location). ancestor dirs of both
    parent and any /System/... symlinks referenced in payload are added
    explicitly so the extractor sees a coherent tree."""
    parent = target.rsplit("/", 1)[0]
    parent_tail = parent.removeprefix("/")

    tree: dict[str, tuple[str, bytes]] = {
        "META-INF": ("d", b""),
        "META-INF/com.apple.ZipMetadata.plist":
            ("f", plistlib.dumps({"Version": 2}, fmt=plistlib.FMT_BINARY)),
        "p0": ("d", b""),
        "p0/p1": ("d", b""),
        "p0/p1/p2": ("d", b""),
        "p0/p1/p2/link": ("l", ("../../../" + parent_tail).encode()),
    }

    def add_dirs(path: str) -> None:
        cursor = ""
        for part in path.split("/"):
            cursor += ("/" if cursor else "") + part
            tree.setdefault(cursor, ("d", b""))

    add_dirs(parent_tail)

    if payload is not None:
        add_dirs(PAYLOAD_PATH)
        for kind, data in payload.values():
            if kind == "l" and data.startswith(SYMLINK_SYSTEM_PREFIX.encode()):
                name = data.decode().removeprefix(SYMLINK_SYSTEM_PREFIX)
                if re.fullmatch(r"[A-Za-z0-9_]+\.bundle", name):
                    add_dirs("System/Library/Carrier Bundles/iPhone/" + name)
        for n, v in payload.items():
            tree[PAYLOAD_PATH + "/" + n] = v

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", allowZip64=False) as z:
        for name in sorted(tree):
            kind, data = tree[name]
            z.writestr(_zip_entry_for(name, kind), data)
    return buf.getvalue()


async def _afc_exists(afc, path: str):
    try:
        return await afc.stat(path)
    except Exception:
        return None


async def afc_tree(afc, root: str) -> dict:
    """flat tree of `root`. keys are slash-paths relative to root. entries:
       ('f', bytes)  regular file contents
       ('l', bytes)  symlink target as bytes
       ('d', b'')    directory marker (empty bytes)
    """
    tree: dict[str, tuple[str, bytes]] = {}
    total_bytes = 0

    async def visit(path: str, name: str, depth: int):
        nonlocal total_bytes
        require(depth < 32 and len(tree) < MAX_NODES, "remote tree limit exceeded")
        info = await _afc_exists(afc, path)
        require(info is not None, f"vanished during listing: {path}")
        kind = info["st_ifmt"]
        if kind == "S_IFDIR":
            if name:
                tree[name] = ("d", b"")
            children = sorted(await afc.listdir(path))
            for child in children:
                if child in ("", ".", ".."): continue
                _safe_component(child)
                await visit(f"{path}/{child}", f"{name}/{child}" if name else child,
                            depth + 1)
            require(children == sorted(await afc.listdir(path)),
                    f"remote directory changed during read: {path}")
        elif kind == "S_IFLNK":
            require(name, "root cannot be a symlink")
            require("LinkTarget" in info, f"symlink without target: {path}")
            tree[name] = ("l", str(info["LinkTarget"]).encode())
        elif kind == "S_IFREG":
            require(name, "root cannot be a file")
            size = int(info.get("st_size", 0))
            require(size <= MAX_BYTES, f"file too large: {path}")
            data = await afc.get_file_contents(path)
            require(len(data) == size, f"remote size mismatch: {path}")
            total_bytes += len(data)
            require(total_bytes <= MAX_BYTES, "total tree size exceeded")
            tree[name] = ("f", data)
        else:
            raise OpError(f"unsupported fs entry at {path}: {kind}")

    root_info = await _afc_exists(afc, root)
    require(root_info and root_info["st_ifmt"] == "S_IFDIR",
            f"remote root is not a directory: {root}")
    await visit(root, "", 0)
    _validate_tree(tree)
    return tree


async def _books_snapshot(afc, run: Path) -> tuple[dict, dict]:
    snap: dict[str, bytes] = {}
    existed: dict[str, bool] = {}
    for path in BOOK_FILES:
        info = await _afc_exists(afc, path)
        existed[path] = info is not None
        if info is not None:
            snap[path] = await afc.get_file_contents(path)
    (run / "books-snapshot.bin").write_bytes(
        plistlib.dumps({k: v for k, v in snap.items()}, fmt=plistlib.FMT_BINARY))
    return snap, existed


async def _restore_books(afc, snap: dict, existed: dict):
    for path in reversed(BOOK_FILES):
        if not existed.get(path):
            try: await afc.rm(path)
            except Exception: pass
    for d in BOOK_DIRS:
        try: await afc.makedirs(d)
        except Exception: pass
    for path, data in snap.items():
        try: await afc.set_file_contents(path, data)
        except Exception: pass


class AirTrafficHost:
    """runtime ctypes wrapper over private AirTrafficHost.framework on macOS."""

    def __init__(self):
        require(sys.platform == "darwin",
                "airlift only runs on macOS (needs AirTrafficHost.framework)")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.at = C.CDLL("/System/Library/PrivateFrameworks/AirTrafficHost.framework/AirTrafficHost")
        self.objc = C.CDLL("/usr/lib/libobjc.A.dylib")
        self.objc.objc_autoreleasePoolPush.restype = C.c_void_p
        self.objc.objc_autoreleasePoolPush.argtypes = []
        self.objc.objc_autoreleasePoolPop.argtypes = [C.c_void_p]
        self.objc.objc_autoreleasePoolPop.restype = None
        self.pool = self.objc.objc_autoreleasePoolPush()
        P, I, U = C.c_void_p, C.c_ssize_t, C.c_size_t
        def bind(lib, name, result, args):
            f = getattr(lib, name); f.restype = result; f.argtypes = args
        for name, result, args in [
            ("CFDataCreate", P, [P, P, I]),
            ("CFDataGetLength", I, [P]),
            ("CFDataGetBytePtr", P, [P]),
            ("CFRelease", None, [P]),
            ("CFPropertyListCreateWithData", P, [P, P, U, P, P]),
            ("CFPropertyListCreateData", P, [P, P, I, U, P]),
        ]:
            bind(self.cf, name, result, args)
        for name, result, args in [
            ("ATHostConnectionCreate", P, [P]),
            ("ATHostConnectionRelease", None, [P]),
            ("ATHostConnectionReadMessage", P, [P]),
            ("ATHostConnectionSendHostInfo", None, [P, P]),
            ("ATHostConnectionSendSyncRequest", None, [P, P, P, P]),
            ("ATHostConnectionSendMetadataSyncFinished", None, [P, P, P]),
            ("ATHostConnectionSendAssetCompleted", None, [P, P, P, P]),
            ("ATCFMessageGetName", P, [P]),
            ("ATCFMessageGetParam", P, [P, P]),
        ]:
            bind(self.at, name, result, args)

    def encode(self, value):
        raw = plistlib.dumps(value, fmt=plistlib.FMT_BINARY)
        buf = C.create_string_buffer(raw)
        data = self.cf.CFDataCreate(None, buf, len(raw))
        require(data, "CFDataCreate failed")
        try:
            result = self.cf.CFPropertyListCreateWithData(None, data, 0, None, None)
            require(result, "CFPropertyListCreateWithData failed")
            return result
        finally:
            self.cf.CFRelease(data)

    def decode(self, ref):
        require(ref, "empty CF ref")
        data = self.cf.CFPropertyListCreateData(None, ref, 200, 0, None)
        require(data, "CFPropertyListCreateData failed")
        try:
            size = self.cf.CFDataGetLength(data)
            require(0 <= size <= MAX_BYTES, "CF payload too large")
            return plistlib.loads(C.string_at(self.cf.CFDataGetBytePtr(data), size))
        finally:
            self.cf.CFRelease(data)

    def call(self, name, connection, *values):
        refs = []
        try:
            for v in values: refs.append(self.encode(v))
            return getattr(self.at, name)(connection, *refs)
        finally:
            for ref in refs: self.cf.CFRelease(ref)

    def close(self):
        if self.pool is not None:
            self.objc.objc_autoreleasePoolPop(self.pool)
            self.pool = None


def _at_host_session(udid: str, assets: list[tuple[str, str]],
                     pre_final: Callable[[], None] | None = None,
                     pre_final_index: int | None = None):
    host = AirTrafficHost()
    connection = None
    try:
        ref = host.encode(udid)
        try:
            connection = host.at.ATHostConnectionCreate(ref)
        finally:
            host.cf.CFRelease(ref)
        require(connection, "AirTraffic connection failed — close finder/itunes sync")

        def wait_for(name: str, limit: int):
            for _ in range(limit):
                msg = host.at.ATHostConnectionReadMessage(connection)
                if not msg: continue
                try:
                    got = host.decode(host.at.ATCFMessageGetName(msg))
                    if got == name:
                        if name != "AssetManifest": return True
                        key = host.encode("AssetManifest")
                        try: return host.decode(host.at.ATCFMessageGetParam(msg, key))
                        finally: host.cf.CFRelease(key)
                    require(got not in ("SyncFailed", "SyncFinished"),
                            "AT sync ended prematurely")
                finally:
                    host.cf.CFRelease(msg)
            raise OpError(f"AT: never received {name}")

        wait_for("SyncAllowed", 8)
        info = {
            "Type": "iTunes", "Version": "13.7.0.161",
            "SyncHostName": "airtweaks", "LibraryID": str(uuid.uuid4()),
            "SyncedDataclasses": ["Book"], "SyncedAssetTypes": ["Book"],
            "Wakeable": False, "MacOSVersion": platform.mac_ver()[0],
        }
        host.call("ATHostConnectionSendHostInfo", connection, info)
        time.sleep(0.2)
        host.call("ATHostConnectionSendSyncRequest", connection, ["Book"], {}, info)
        wait_for("ReadyForSync", 12)
        host.call("ATHostConnectionSendMetadataSyncFinished", connection, {"Book": 1}, {})
        manifest = wait_for("AssetManifest", 20)
        require(isinstance(manifest, dict), "AT: bad manifest")
        found = {r.get("AssetID") for r in manifest.get("Book", [])
                 if isinstance(r, dict) and r.get("IsDownload")}
        require(all(a in found for a, _ in assets),
                "AT: manifest missing our assets")
        for i, (identifier, destination) in enumerate(assets):
            if pre_final is not None and i == pre_final_index:
                pre_final()
            host.call("ATHostConnectionSendAssetCompleted", connection,
                      identifier, "Book", destination)
            if i + 1 < len(assets):
                time.sleep(0.9)
        time.sleep(2)
    finally:
        if connection:
            host.at.ATHostConnectionRelease(connection)
        host.close()


async def _at_host_session_async(udid: str, assets, pre_final=None,
                                 pre_final_index: int | None = None):
    loop = asyncio.get_event_loop()
    _pre = None
    if pre_final is not None:
        def _pre():
            fut = asyncio.run_coroutine_threadsafe(pre_final(), loop)
            fut.result()
    await loop.run_in_executor(None, _at_host_session, udid, assets, _pre,
                               pre_final_index)


async def transfer(device, run: Path, target: str,
                   payload: dict | None = None,
                   expected: dict | None = None) -> dict:
    """airlift transfer for `target` (a /var/mobile/... directory).
       payload=None  → snapshot only (returns current tree at target)
       payload=dict  → write payload to target, then verify readback
       expected      → optional; abort if pre-write tree differs
    """
    from pymobiledevice3.services.afc import AfcService
    run.mkdir(parents=True, exist_ok=False)

    tail = target.removeprefix("/var/mobile/")
    parent_tail = target.rsplit("/", 1)[0].removeprefix("/")
    basename = target.rsplit("/", 1)[-1]

    token = os.urandom(10).hex()
    source, link, exported = (f"airlift-{t}-{token}" for t in ("src", "link", "saved"))
    final_source = source + "/" + PAYLOAD_PATH if payload is not None else exported
    assets_ids = [
        (f"../../{source}/p0/p1/p2/link", link),
        ("../../../" + tail, exported),
        (f"../../{final_source}", link + "/" + basename),
    ]

    snapshot = None
    async with AfcService(device) as afc:
        for p in (source, link, exported):
            require(await _afc_exists(afc, p) is None, "staging path collision")
        books, existed = await _books_snapshot(afc, run)
        mutated = False
        try:
            raw = _staging_archive(payload, target)
            (run / "staging.zip").write_bytes(raw)
            if payload is not None:
                write_tree_zip(run / "desired.zip", payload)
            mutated = True

            svc = await device.start_lockdown_service("com.apple.streaming_zip_conduit")
            try:
                await svc.send_plist({"MediaSubdir": source}, fmt=plistlib.FMT_BINARY)
                await svc.sendall(raw)
                reply = await asyncio.wait_for(svc.recv_plist(), 30)
                require(reply.get("Status") == "DataComplete",
                        "streaming-zip rejected by device")
            finally:
                await svc.close()

            node = await afc.stat(source + "/p0/p1/p2/link")
            require(node["st_ifmt"] == "S_IFLNK"
                    and node.get("LinkTarget") == "../../../" + parent_tail,
                    "staged escape-link mismatch")
            if payload is not None:
                got = await afc_tree(afc, source + "/" + PAYLOAD_PATH)
                require(got == payload, "staged payload mismatch")

            await afc.makedirs("Books/Sync")
            books_meta = plistlib.dumps({"Books": [
                {"Persistent ID": a, "Item ID": str(i), "DSID": "1"}
                for i, (a, _) in enumerate(assets_ids, 1)
            ]}, fmt=plistlib.FMT_BINARY)
            await afc.set_file_contents("Books/Sync/Books.plist", books_meta)

            async def pre_final():
                nonlocal snapshot
                for _ in range(40):
                    if await _afc_exists(afc, exported): break
                    await asyncio.sleep(0.1)
                node = await _afc_exists(afc, exported)
                require(node and node["st_ifmt"] == "S_IFDIR",
                        "no exported catalog (recovery required)")
                snapshot = await afc_tree(afc, exported)
                write_tree_zip(run / "original.zip", snapshot)
                if expected is not None:
                    require(snapshot == expected,
                            "target changed since snapshot; abort")

            await _at_host_session_async(device.udid, assets_ids, pre_final,
                                         pre_final_index=2)

            for _ in range(30):
                if await _afc_exists(afc, final_source) is None: break
                await asyncio.sleep(0.1)
            require(await _afc_exists(afc, final_source) is None,
                    "final source not consumed — unconfirmed")
        finally:
            if mutated:
                try: await _restore_books(afc, books, existed)
                except Exception as e:
                    raise OpError(f"books-restore failed: {e}") from e
    return snapshot


async def write_files_atomic(device, run: Path, target_dir: str,
                             files: dict[str, bytes]) -> None:
    """write specific files INTO target_dir via airlift, preserving the parent
    directory inode. safe for dirs with live-daemon FDs (unlike transfer()
    which swaps the whole dir). each named file is created or replaced;
    files not named are left untouched."""
    require(files, "no files to write")
    from pymobiledevice3.services.afc import AfcService
    run.mkdir(parents=True, exist_ok=False)

    tail = target_dir.removeprefix("/var/mobile/")
    token = os.urandom(10).hex()
    source, link = (f"airlift-{t}-{token}" for t in ("src", "link"))
    names = sorted(files.keys())
    for n in names: _safe_component(n)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", allowZip64=False) as z:
        z.writestr(_zi("META-INF/", stat.S_IFDIR | 0o755), b"")
        z.writestr(_zi("META-INF/com.apple.ZipMetadata.plist", stat.S_IFREG | 0o600),
                   plistlib.dumps({"Version": 2}, fmt=plistlib.FMT_BINARY, sort_keys=True))
        for d in ("p0/", "p0/p1/", "p0/p1/p2/"):
            z.writestr(_zi(d, stat.S_IFDIR | 0o755), b"")
        z.writestr(_zi("p0/p1/p2/link", stat.S_IFLNK | 0o777),
                   b"../../../" + tail.encode())
        for i, n in enumerate(names):
            z.writestr(_zi(f"payload_{i}", stat.S_IFREG | 0o600), files[n])
    raw = buf.getvalue()

    assets_ids: list[tuple[str, str]] = [
        (f"../../{source}/p0/p1/p2/link", link),
    ]
    for i, n in enumerate(names):
        assets_ids.append((f"../../{source}/payload_{i}", f"{link}/{n}"))

    async with AfcService(device) as afc:
        for p in (source, link):
            require(await _afc_exists(afc, p) is None, "staging path collision")
        books, existed = await _books_snapshot(afc, run)
        try:
            (run / "staging.zip").write_bytes(raw)
            svc = await device.start_lockdown_service("com.apple.streaming_zip_conduit")
            try:
                await svc.send_plist({"MediaSubdir": source}, fmt=plistlib.FMT_BINARY)
                await svc.sendall(raw)
                reply = await asyncio.wait_for(svc.recv_plist(), 30)
                require(reply.get("Status") == "DataComplete",
                        "streaming-zip rejected by device")
            finally:
                await svc.close()

            node = await afc.stat(source + "/p0/p1/p2/link")
            require(node["st_ifmt"] == "S_IFLNK"
                    and node.get("LinkTarget") == "../../../" + tail,
                    "staged escape-link mismatch")

            await afc.makedirs("Books/Sync")
            books_meta = plistlib.dumps({"Books": [
                {"Persistent ID": a, "Item ID": str(i), "DSID": "1"}
                for i, (a, _) in enumerate(assets_ids, 1)
            ]}, fmt=plistlib.FMT_BINARY)
            await afc.set_file_contents("Books/Sync/Books.plist", books_meta)

            await _at_host_session_async(device.udid, assets_ids)
        finally:
            try: await _restore_books(afc, books, existed)
            except Exception as e:
                raise OpError(f"books-restore failed: {e}") from e


async def connect(udid: str, *, wait_seconds: int = 5):
    """open a lockdown connection over whatever transport is available.
    prefers USB when both are paired (lower latency for airlift). all lockdown
    services + AirTraffic ceremony work over network too."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.usbmux import list_devices
    devices = await list_devices()
    matches = [d for d in devices if d.serial == udid]
    require(matches, f"device {udid} not visible in usbmux")
    match = next((d for d in matches if d.connection_type == "USB"), matches[0])
    return await asyncio.wait_for(
        create_using_usbmux(serial=udid, autopair=False,
                            connection_type=match.connection_type),
        wait_seconds + 10,
    )


def digest_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
