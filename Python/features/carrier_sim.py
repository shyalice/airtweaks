"""carrier bundle swap — plants IMSI→donor.bundle symlinks under
/var/mobile/Library/Carrier Bundles/iPhone/ via airlift, then triggers a
commcenter re-scan by installing a signed IPCC.
"""
from __future__ import annotations
import asyncio
import io
import json
import os
import plistlib
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from features._airlift import (
    OpError, require, transfer, connect, digest_sha256,
    AirTrafficHost,
)


HERE = Path(__file__).resolve().parent
_MEIPASS = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None) else None
ASSETS_CANDIDATES = [
    HERE / "carrier_assets.zip",
    (_MEIPASS / "features" / "carrier_assets.zip") if _MEIPASS else None,
    (_MEIPASS / "carrier_assets.zip") if _MEIPASS else None,
]
ASSETS_PATH = next((p for p in ASSETS_CANDIDATES if p and p.is_file()), None)
ASSETS_SHA = "6de1ea0be81a29c145ef414f24bc21d1dcb8a4eb737b22b1f956e9a6f0c2098b"

TARGET = "/var/mobile/Library/Carrier Bundles/iPhone"
# relative symlink content — resolves from /var/mobile/Library/Carrier Bundles/iPhone/
# up 6 levels to / then into System/... . absolute /System/... is rejected by
# streaming_zip target-validation, hence the relative form.
SYSTEM_PREFIX = "../../../../../../System/Library/Carrier Bundles/iPhone/"
BUNDLES_ROOT = Path("/Users/rei/Desktop/carrier/ios-carrier-bundle/carrier-bundles")

TRIGGER_NAMES = ("AVEA_tr.ipcc", "Swisscom_ch.ipcc", "O2_Germany.ipcc")


def emit(kind: str, **payload):
    print(json.dumps({"type": kind, **payload}, default=str), flush=True)


def log(level: str, msg: str):
    emit("log", level=level, message=msg)


def die(msg: str, **extra):
    emit("result", ok=False, exit_code=1, error=msg, **extra)


def load_assets() -> dict:
    require(ASSETS_PATH is not None, "carrier_assets.zip missing")
    raw = ASSETS_PATH.read_bytes()
    require(digest_sha256(raw) == ASSETS_SHA,
            "carrier_assets.zip tampered (sha256 mismatch)")
    out = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            if info.is_dir(): continue
            out[info.filename] = ("f", z.read(info))
    return out


def _check_trigger(ipcc: Path, plmns: set[str]):
    with zipfile.ZipFile(ipcc) as z:
        for info in z.infolist():
            if info.filename.endswith("/carrier.plist"):
                d = plistlib.loads(z.read(info))
                overlap = set(d.get("SupportedSIMs", [])) & plmns
                if overlap:
                    raise OpError(f"trigger overlaps PLMN {overlap} — pick another")


def pick_trigger(assets: dict, plmns: set[str], workdir: Path) -> Path:
    for name in TRIGGER_NAMES:
        entry = assets.get(f"triggers/{name}")
        if not entry: continue
        dst = workdir / name
        dst.write_bytes(entry[1])
        try:
            _check_trigger(dst, plmns)
            return dst
        except OpError:
            dst.unlink(missing_ok=True)
    raise OpError("no non-overlapping trigger IPCC for these SIMs")


async def install_trigger(device, ipcc_path: Path):
    from pymobiledevice3.services.afc import AfcService
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    remote_name = f"airtweaks-trigger-{os.urandom(4).hex()}.ipcc"
    async with AfcService(device) as afc:
        try: await afc.makedirs("PublicStaging")
        except Exception: pass
        remote = f"PublicStaging/{remote_name}"
        try: await afc.rmtree(remote)
        except Exception: pass
        await afc.set_file_contents(remote, ipcc_path.read_bytes())

    proxy = InstallationProxyService(device)
    async with proxy:
        try:
            await proxy.send_package(
                "Install", {"PackageType": "CarrierBundle"}, None,
                f"PublicStaging/{remote_name}",
            )
        except Exception:
            # apple returns "error" when the trigger IPCC doesn't bind any
            # real SIM — the commcenter re-scan side-effect still fires
            pass


def select_sims(rows: list[dict], donor: str | None) -> list[dict]:
    picked = []
    seen_slots, seen_imsi = set(), set()
    for r in rows:
        slot = r.get("Slot")
        mcc, mnc = str(r.get("MCC", "")), str(r.get("MNC", ""))
        imsi = r.get("InternationalMobileSubscriberIdentity")
        require(slot in ("kOne", "kTwo") and slot not in seen_slots,
                "ambiguous SIM slot")
        require(re.fullmatch(r"\d{3}", mcc)
                and re.fullmatch(r"\d{2,3}", mnc)
                and isinstance(imsi, str)
                and re.fullmatch(r"\d{15}", imsi)
                and imsi.startswith(mcc + mnc),
                f"phone did not report a full IMSI for SIM {mcc}{mnc} — "
                "unlock the phone and try again")
        require(imsi not in seen_imsi, "duplicate IMSI across slots")
        seen_slots.add(slot); seen_imsi.add(imsi)
        picked.append({"slot": slot, "plmn": mcc + mnc, "imsi": imsi, "bundle": donor})
    require(picked, "phone reported no SIMs with usable IMSI")
    return picked


def make_plan(original: dict, sims: list[dict], donor: str) -> dict:
    desired = dict(original)
    target_link = ("l", (SYSTEM_PREFIX + donor).encode())
    for s in sims:
        imsi = s["imsi"]
        if imsi in original:
            require(original[imsi][0] == "l",
                    f"IMSI {imsi} is a file/dir on device, not a symlink")
        desired[imsi] = target_link
    return desired


def strip_imsi_links(original: dict) -> dict:
    return {n: v for n, v in original.items()
            if not (v[0] == "l" and re.fullmatch(r"\d{15}", n))}


def list_donors_action():
    preferred = "26.6.2-23G90.V53_V54_V57OS"
    build = BUNDLES_ROOT / preferred
    seen: dict[str, str] = {}
    def scan(d: Path, tag: str):
        if not d.is_dir(): return
        for p in sorted(d.iterdir()):
            if p.is_dir() and p.name.endswith(".bundle") and p.name not in seen:
                seen[p.name] = tag
    if build.is_dir():
        scan(build, preferred)
    elif BUNDLES_ROOT.is_dir():
        for d in sorted(BUNDLES_ROOT.iterdir()):
            scan(d, d.name)
    emit("result", ok=True,
         donors=[{"file": n} for n in sorted(seen.keys())],
         source=str(build if build.is_dir() else BUNDLES_ROOT))


def _label_slot(slot: str) -> str:
    return {"kOne": "sim 1", "kTwo": "sim 2"}.get(slot, slot)


def bundle_id(row: dict) -> str | None:
    """CarrierBundleInfoArray key was BundleIdentifier pre-iOS-26; now CFBundleIdentifier."""
    return row.get("CFBundleIdentifier") or row.get("BundleIdentifier")


async def flow_status(udid: str) -> int:
    log("info", "connecting …")
    device = await connect(udid)
    try:
        rows = await device.get_value(key="CarrierBundleInfoArray") or []
        pv = await device.get_value(key="ProductVersion")
        bv = await device.get_value(key="BuildVersion")
        pt = await device.get_value(key="ProductType")
        log("ok", f"{pt} · ios {pv} ({bv}) · {len(rows)} sim(s)")
        for r in rows:
            slot = _label_slot(r.get("Slot"))
            plmn = f"{r.get('MCC','')}{r.get('MNC','')}"
            bundle = bundle_id(r) or "?"
            short = bundle.removeprefix("com.apple.") if bundle != "?" else "?"
            ver = r.get("CFBundleVersion") or ""
            log("info", f"{slot} · plmn {plmn} · {short}"
                        + (f" (v{ver})" if ver else ""))
        emit("result", ok=True, exit_code=0, action="status",
             sims=[{"slot": r.get("Slot"),
                    "plmn": f"{r.get('MCC','')}{r.get('MNC','')}",
                    "bundle": bundle_id(r),
                    "iccid": r.get("IntegratedCircuitCardIdentity"),
                    "imsi": r.get("InternationalMobileSubscriberIdentity")} for r in rows])
        return 0
    finally:
        try: await device.close()
        except Exception: pass


async def flow_apply_or_restore(udid: str, donor: str | None,
                                is_restore: bool, workdir: Path) -> int:
    log("info", "connecting …")
    device = await connect(udid)
    try:
        rows = await device.get_value(key="CarrierBundleInfoArray") or []
        sims = select_sims(rows, None if is_restore else donor)
        for s in sims:
            slot = _label_slot(s["slot"])
            what = "restore stock" if is_restore else f"map to {donor}"
            log("info", f"{slot} · plmn {s['plmn']} → {what}")

        assets = load_assets()
        plmns = {f"{r.get('MCC','')}{r.get('MNC','')}" for r in rows}
        trigger = pick_trigger(assets, plmns, workdir)
        log("debug", f"trigger ipcc: {trigger.name}")

        run_dir = workdir / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
        run_dir.mkdir(mode=0o700)

        log("info", "[1/4] priming commcenter rescan …")
        await install_trigger(device, trigger)

        log("info", "[2/4] snapshotting carrier bundles …")
        original = await transfer(device, run_dir / "snapshot", target=TARGET)
        log("ok", f"snapshot: {len(original)} entries")

        if is_restore:
            desired = strip_imsi_links(original)
            log("info", f"[3/4] removing {len(original)-len(desired)} imsi symlink(s) …")
        else:
            re_sims = select_sims(await device.get_value(key="CarrierBundleInfoArray") or [], donor)
            require(re_sims == sims, "sim state changed during the operation")
            desired = make_plan(original, sims, donor)
            log("info", f"[3/4] writing {len(desired)-len(original)} new imsi symlink(s) …")

        await transfer(device, run_dir / "write", target=TARGET,
                       payload=desired, expected=original)
        readback = await transfer(device, run_dir / "readback", target=TARGET)
        require(readback == desired, "readback mismatch — device state didn't converge")
        log("ok", "readback verified")

        log("info", "[4/4] triggering commcenter re-scan + signature check …")
        await install_trigger(device, trigger)

        rows2 = await device.get_value(key="CarrierBundleInfoArray") or []
        result = []
        for s in sims:
            r2 = next((r for r in rows2 if r.get("Slot") == s["slot"]), None)
            got_bundle = bundle_id(r2) if r2 else None
            expected = None if is_restore else donor.replace(".bundle", "")
            expected_bundle_id = f"com.apple.{expected}" if expected else None
            _ = expected_bundle_id  # keep the linter quiet; used below
            verified = ((got_bundle == expected_bundle_id) if not is_restore
                        else (got_bundle != f"com.apple.{donor.replace('.bundle','')}"
                              if donor else True))
            result.append({"slot": s["slot"], "plmn": s["plmn"],
                           "expected": expected_bundle_id, "got": got_bundle,
                           "verified": bool(verified)})
            slot = _label_slot(s["slot"])
            if verified:
                log("ok", f"{slot} ({s['plmn']}): bundle now {got_bundle}")
            else:
                log("warn", f"{slot} ({s['plmn']}): expected {expected_bundle_id}, got {got_bundle}")

        unconfirmed = any(not r["verified"] for r in result)
        if is_restore:
            log("ok", "imsi symlinks stripped — stock carrier restored")
        else:
            log("ok", "done — toggle airplane mode ~15 s to reattach")

        rc = 2 if unconfirmed else 0
        emit("result", ok=(rc == 0), exit_code=rc,
             action=("restore" if is_restore else "apply"), slots=result)
        return rc
    finally:
        try: await device.close()
        except Exception: pass


async def _drive(params: dict) -> int:
    action = params.get("action", "apply")
    if action == "list_donors":
        list_donors_action(); return 0

    if action == "check":
        try:
            assets = load_assets()
            require("triggers/AVEA_tr.ipcc" in assets, "trigger IPCCs missing from assets")
            AirTrafficHost().close()
            log("ok", "assets ok, airtraffichost.framework loads ok")
            emit("result", ok=True, exit_code=0, action="check")
            return 0
        except OpError as e:
            die(str(e)); return 1

    udid = params.get("udid")
    if not udid:
        die("missing udid"); return 1

    donor = params.get("donor")
    if action == "apply" and not donor:
        die("apply requires donor"); return 1

    workdir = Path(tempfile.mkdtemp(prefix="airtweaks-carrier-"))
    try:
        if action == "status":
            return await flow_status(udid)
        if action == "apply":
            return await flow_apply_or_restore(udid, donor, False, workdir)
        if action == "restore":
            return await flow_apply_or_restore(udid, None, True, workdir)
        die(f"unknown action: {action}"); return 1
    except OpError as e:
        die(str(e)); return 1
    finally:
        try:
            keep = any(p.is_dir() and any(p.iterdir()) for p in workdir.iterdir())
        except Exception:
            keep = False
        if not keep:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            log("debug", f"work dir kept: {workdir}")


def run(params: dict) -> None:
    try:
        asyncio.run(_drive(params))
    except OpError as e:
        die(str(e))
    except Exception as e:
        import traceback
        die(f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=8))


if __name__ == "__main__":
    try:
        params = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        die(f"bad stdin json: {e}"); sys.exit(1)
    run(params)
