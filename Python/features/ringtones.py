#!/usr/bin/env python3
"""Push a .m4r ringtone into iOS custom-ringtones dir via pymobiledevice3 AFC.

Actions on stdin:
    { "udid": ..., "action": "list" }
    { "udid": ..., "action": "push",
      "source_path": "/local.m4r", "remote_name": "MyTone.m4r" }
    { "udid": ..., "action": "delete", "remote_name": "MyTone.m4r" }
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

RINGTONES_DIR = "iTunes_Control/Ringtones"


def emit(kind: str, **payload):
    print(json.dumps({"type": kind, **payload}, default=str), flush=True)


def log(level: str, msg: str):
    emit("log", level=level, message=msg)


async def _afc(udid: str):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService
    ld = await create_using_usbmux(serial=udid)
    return AfcService(ld)


async def list_tones(udid: str) -> None:
    svc = await _afc(udid)
    async with svc:
        try:
            entries = await svc.listdir(RINGTONES_DIR)
        except Exception as e:
            emit("result", ok=False, exit_code=1, error=f"list failed: {e}"); return
    names = [Path(e).name for e in entries]
    tones = [n for n in names if n.endswith((".m4r", ".m4a"))]
    emit("result", ok=True, exit_code=0, tones=sorted(tones))


async def push_tone(udid: str, source: Path, remote_name: str) -> None:
    if not source.is_file():
        emit("result", ok=False, exit_code=1, error=f"source not found: {source}"); return
    remote = f"{RINGTONES_DIR}/{remote_name}"
    log("info", f"AFC push {source.name} → {remote}")
    svc = await _afc(udid)
    async with svc:
        try:
            data = source.read_bytes()
            await svc.set_file_contents(remote, data)
        except Exception as e:
            emit("result", ok=False, exit_code=1, error=f"push failed: {e}"); return
    emit("result", ok=True, exit_code=0,
         remote_path=f"/var/mobile/Media/{remote}",
         hint="MediaLibrary rescans on next Settings > Sound open")


async def delete_tone(udid: str, remote_name: str) -> None:
    remote = f"{RINGTONES_DIR}/{remote_name}"
    log("info", f"AFC rm {remote}")
    svc = await _afc(udid)
    async with svc:
        try:
            await svc.rm(remote)
        except Exception as e:
            emit("result", ok=False, exit_code=1, error=f"rm failed: {e}"); return
    emit("result", ok=True, exit_code=0)


async def _run(params: dict) -> None:
    udid = params.get("udid")
    if not udid:
        emit("result", ok=False, exit_code=1, error="missing udid"); return
    action = params.get("action")
    if action == "list":
        await list_tones(udid)
    elif action == "push":
        await push_tone(udid, Path(params["source_path"]),
                        params.get("remote_name") or Path(params["source_path"]).name)
    elif action == "delete":
        await delete_tone(udid, params["remote_name"])
    else:
        emit("result", ok=False, exit_code=1, error=f"unknown action: {action}")


def run(params: dict) -> None:
    asyncio.run(_run(params))


if __name__ == "__main__":
    try:
        params = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        emit("result", ok=False, exit_code=1, error=f"bad stdin json: {e}"); sys.exit(1)
    try:
        run(params)
    except Exception as e:
        import traceback
        emit("result", ok=False, exit_code=1,
             error=f"{type(e).__name__}: {e}",
             trace=traceback.format_exc(limit=6))
        sys.exit(1)
