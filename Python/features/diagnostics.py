#!/usr/bin/env python3
"""Diagnostics via pymobiledevice3 library (in-process).

Works in both dev (system python with pip-installed pymobiledevice3) and
frozen PyInstaller bundle (library included). No dependency on the CLI.

Actions on stdin:
    device_info | baseband_info | battery | storage | installed_apps
    | reboot | shutdown
"""
from __future__ import annotations
import asyncio
import json
import sys


def emit(kind: str, **payload):
    print(json.dumps({"type": kind, **payload}, default=str), flush=True)


def log(level: str, msg: str):
    emit("log", level=level, message=msg)


async def _lockdown(udid: str):
    from pymobiledevice3.lockdown import create_using_usbmux
    return await create_using_usbmux(serial=udid)


async def device_info(udid: str):
    ld = await _lockdown(udid)
    info = {}
    domains = [None,
               "com.apple.mobile.battery",
               "com.apple.disk_usage",
               "com.apple.mobile.wireless_lockdown"]
    for d in domains:
        try:
            info[d or "GLOBAL"] = (await ld.get_value(domain=d)) if d \
                else (await ld.get_value())
        except Exception as e:
            info[d or "GLOBAL"] = f"<err: {e}>"
    emit("result", ok=True, exit_code=0, info=info)


async def baseband_info(udid: str):
    ld = await _lockdown(udid)
    g = await ld.get_value()
    keys = ["BasebandChipID", "BasebandCertId", "BasebandKeyHashInformation",
            "BasebandMasterKeyHash", "BasebandRegionSKU", "BasebandSerialNumber",
            "BasebandStatus", "BasebandVersion", "CellularBundleVersion",
            "CarrierBundleInfoArray",
            "InternationalMobileEquipmentIdentity",
            "InternationalMobileEquipmentIdentity2",
            "InternationalMobileSubscriberIdentity",
            "InternationalMobileSubscriberIdentity2",
            "MobileSubscriberCountryCode", "MobileSubscriberNetworkCode",
            "PhoneNumber", "SIMStatus", "SIMTrayStatus"]
    emit("result", ok=True, exit_code=0,
         info={k: g[k] for k in keys if k in g})


async def battery(udid: str):
    ld = await _lockdown(udid)
    d = await ld.get_value(domain="com.apple.mobile.battery")
    emit("result", ok=True, exit_code=0, info=d)


async def storage(udid: str):
    ld = await _lockdown(udid)
    d = await ld.get_value(domain="com.apple.disk_usage")
    emit("result", ok=True, exit_code=0, info=d)


async def installed_apps(udid: str):
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    ld = await _lockdown(udid)
    svc = InstallationProxyService(ld)
    async with svc:
        try:
            got = await svc.get_apps(app_types=["User", "System"])
        except TypeError:
            got = await svc.get_apps()
    apps = []
    if isinstance(got, dict):
        for bid, meta in got.items():
            if not isinstance(meta, dict): continue
            apps.append({
                "bundle_id": bid,
                "name": meta.get("CFBundleDisplayName") or meta.get("CFBundleName") or bid,
                "version": meta.get("CFBundleShortVersionString") or meta.get("CFBundleVersion") or "",
                "type": meta.get("ApplicationType", "?"),
            })
    apps.sort(key=lambda x: x["name"].lower())
    emit("result", ok=True, exit_code=0, apps=apps, count=len(apps))


async def reboot(udid: str):
    from pymobiledevice3.services.diagnostics import DiagnosticsService
    ld = await _lockdown(udid)
    svc = DiagnosticsService(ld)
    async with svc:
        await svc.restart()
    emit("result", ok=True, exit_code=0, message="restart issued")


async def shutdown(udid: str):
    from pymobiledevice3.services.diagnostics import DiagnosticsService
    ld = await _lockdown(udid)
    svc = DiagnosticsService(ld)
    async with svc:
        await svc.shutdown()
    emit("result", ok=True, exit_code=0, message="shutdown issued")


HANDLERS = {
    "device_info":    device_info,
    "baseband_info":  baseband_info,
    "battery":        battery,
    "storage":        storage,
    "installed_apps": installed_apps,
    "reboot":         reboot,
    "shutdown":       shutdown,
}


async def _run(params: dict) -> None:
    udid = params.get("udid")
    if not udid:
        emit("result", ok=False, exit_code=1, error="missing udid"); return
    action = params.get("action")
    handler = HANDLERS.get(action)
    if handler is None:
        emit("result", ok=False, exit_code=1, error=f"unknown action: {action}"); return
    try:
        await handler(udid)
    except Exception as e:
        import traceback
        emit("result", ok=False, exit_code=1,
             error=f"{type(e).__name__}: {e}",
             trace=traceback.format_exc(limit=6))


def run(params: dict) -> None:
    asyncio.run(_run(params))


if __name__ == "__main__":
    try:
        params = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        emit("result", ok=False, exit_code=1, error=f"bad stdin json: {e}"); sys.exit(1)
    run(params)
