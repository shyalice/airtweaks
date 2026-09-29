"""list attached iphones (usb + network) via pymobiledevice3."""
from __future__ import annotations
import asyncio
import json
import sys


def emit(kind: str, **payload):
    print(json.dumps({"type": kind, **payload}, default=str), flush=True)


async def _list() -> list[dict]:
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux

    out: list[dict] = []
    for d in await list_devices():
        conn = getattr(d, "connection_type", "?") or "?"
        row: dict = {
            "udid": d.serial,
            "connection": conn,
            "name": "iPhone",
            "product_type": "?",
            "product_version": "?",
            "build_version": "?",
        }
        try:
            ld = await create_using_usbmux(serial=d.serial, autopair=False,
                                           connection_type=conn)
            try:
                async def q(k):
                    try: return await ld.get_value(key=k)
                    except Exception: return None
                row["name"] = await q("DeviceName") or "iPhone"
                row["product_type"] = await q("ProductType") or "?"
                row["product_version"] = await q("ProductVersion") or "?"
                row["build_version"] = await q("BuildVersion") or "?"
            finally:
                try: await ld.close()
                except Exception: pass
        except Exception as e:
            row["note"] = f"lockdown failed: {e}"
        out.append(row)
    return out


async def _drive(params: dict) -> None:
    action = params.get("action", "list")
    if action != "list":
        emit("result", ok=False, exit_code=1, error=f"unknown action: {action}"); return
    devices = await _list()
    emit("result", ok=True, exit_code=0, devices=devices)


def run(params: dict) -> None:
    try:
        asyncio.run(_drive(params))
    except Exception as e:
        import traceback
        emit("result", ok=False, exit_code=1,
             error=f"{type(e).__name__}: {e}",
             trace=traceback.format_exc(limit=6))


if __name__ == "__main__":
    try:
        params = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        emit("result", ok=False, exit_code=1, error=f"bad stdin json: {e}"); sys.exit(1)
    run(params)
