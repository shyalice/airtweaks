"""insert a fabricated call into iOS CallHistory.storedata.

read = native `_airlift.transfer` (single AT cycle, ~10s, preserves dir inode).
write = AirCard `write_files_batch` (per-file airlift, proven reliable with
callservicesd's live FDs). AirCard helpers must be built locally at
/Users/rei/Desktop/carrier/AirCard/ — not shipped in the pyinstaller bundle.
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from features._airlift import connect, transfer


HERE = Path(__file__).resolve().parent
AIRCARD_CANDIDATES = [
    Path("/Users/rei/Desktop/carrier/AirCard"),
    HERE.parents[3] / "AirCard",
    HERE.parents[2] / "AirCard",
]
AIRCARD = next((p for p in AIRCARD_CANDIDATES if (p / "apply_card_skin.py").is_file()), None)


def emit(kind: str, **payload):
    print(json.dumps({"type": kind, **payload}, default=str), flush=True)


def log(level: str, msg: str):
    emit("log", level=level, message=msg)


def die(msg: str, **extra):
    emit("result", ok=False, exit_code=1, error=msg, **extra)


if AIRCARD is None:
    def run(_params):
        die("AirCard helpers not found — call_history needs "
            "/Users/rei/Desktop/carrier/AirCard with device_helper + airtraffic_host built")
else:
    sys.path.insert(0, str(AIRCARD))
    import apply_card_skin as ac  # noqa: E402

    DB_DIR = "/var/mobile/Library/CallHistoryDB"
    DB_LEAF = "CallHistory.storedata"
    WAL_LEAF = "CallHistory.storedata-wal"
    SHM_LEAF = "CallHistory.storedata-shm"
    COREDATA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


    def _coredata_now() -> float:
        return (datetime.now(timezone.utc) - COREDATA_EPOCH).total_seconds()


    async def _snapshot_db(udid: str, scratch: Path) -> Path | None:
        device = await connect(udid)
        try:
            snapshot = await transfer(device, scratch / "airlift", target=DB_DIR)
        finally:
            try: await device.close()
            except Exception: pass
        files = scratch / "files"; files.mkdir()
        for name, (kind, data) in snapshot.items():
            if kind == "f":
                (files / name).write_bytes(data)
        if not (files / DB_LEAF).is_file():
            log("error", f"{DB_LEAF} missing from snapshot"); return None
        log("ok", f"pulled {len(snapshot)} files, main={(files / DB_LEAF).stat().st_size} B")
        return files / DB_LEAF


    def _checkpoint_wal(main_path: Path) -> None:
        conn = sqlite3.connect(str(main_path))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            conn.close()


    def _push_db(udid: str, main_path: Path) -> bool:
        payload = main_path.read_bytes()
        files = [(DB_LEAF, payload), (WAL_LEAF, b""), (SHM_LEAF, b"")]
        log("info", f"[3/3] pushing main ({len(payload)} B) + empty wal/shm …")
        return ac.write_files_batch(udid, DB_DIR, files, retries=3, progress_callback=None)


    def _mutate_sqlite(db_path: Path, params: dict) -> None:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cols = {row["name"] for row in cur.execute("PRAGMA table_info(ZCALLRECORD)").fetchall()}
            if not cols:
                raise RuntimeError("ZCALLRECORD missing — wrong DB shape")
            ent_row = cur.execute(
                "SELECT Z_ENT, Z_MAX FROM Z_PRIMARYKEY WHERE Z_NAME='CallRecord'"
            ).fetchone()
            if ent_row is None:
                raise RuntimeError("Z_PRIMARYKEY missing CallRecord entry")
            z_ent, z_max = ent_row["Z_ENT"], ent_row["Z_MAX"]
            next_pk = (z_max or 0) + 1

            minutes_ago = int(params.get("minutes_ago", 0))
            when = _coredata_now() - minutes_ago * 60
            direction = params.get("direction", "incoming")
            originated = 1 if direction == "outgoing" else 0
            answered = 1 if params.get("answered") else 0
            duration = float(params.get("duration_sec", 0)) if answered else 0.0
            number = (params.get("phone_number") or "").strip()
            country = (params.get("iso_country") or "").strip().lower()
            service = params.get("service_provider") or "com.apple.Telephony"
            display_name = params.get("display_name") or None
            initiator = 1 if direction == "outgoing" else 0
            is_facetime = service.startswith("com.apple.FaceTime")
            call_type = (16 if service.endswith(".Audio")
                         else 8 if is_facetime else 1)
            handle_type = 3 if is_facetime else 2
            originating_ui_type = 1 if direction == "outgoing" else 45
            disconnected_cause = (
                0 if direction == "outgoing" and not answered
                else 2 if not answered
                else 41
            )

            local_uuid_bytes = uuid.uuid4().bytes
            line_hex = params.get("line_uuid_hex")
            if line_hex:
                try:
                    local_uuid_bytes = bytes.fromhex(line_hex.replace("-", ""))
                    if len(local_uuid_bytes) != 16:
                        raise ValueError
                except Exception:
                    raise RuntimeError("bad line_uuid_hex")
            unique_id = str(uuid.uuid4()).upper()

            candidate = {
                "Z_PK": next_pk, "Z_ENT": z_ent, "Z_OPT": 1,
                "ZANSWERED": answered,
                "ZCALL_CATEGORY": 2 if is_facetime else 1,
                "ZCALLTYPE": call_type,
                "ZCOMMUNICATIONTRUSTSCORE": 4,
                "ZDISCONNECTED_CAUSE": disconnected_cause,
                "ZFACE_TIME_DATA": 0,
                "ZHANDLE_TYPE": handle_type,
                "ZHASMESSAGE": 0,
                "ZINITIATOR": initiator,
                "ZORIGINATED": originated,
                "ZORIGINATINGUITYPE": originating_ui_type,
                "ZREAD": 0 if (not answered and direction == "incoming") else 1,
                "ZVERIFICATIONSTATUS": 4,
                "ZWASEMERGENCYCALL": 0,
                "ZDATE": when,
                "ZDURATION": duration,
                "ZADDRESS": number,
                "ZISO_COUNTRY_CODE": country,
                "ZSERVICE_PROVIDER": service,
                "ZUNIQUE_ID": unique_id,
                "ZNAME": display_name,
                "ZLOCALPARTICIPANTUUID": local_uuid_bytes,
                "ZOUTGOINGLOCALPARTICIPANTUUID": local_uuid_bytes,
            }
            insert_cols = [c for c in candidate if c in cols or c == "Z_PK"]
            placeholders = ", ".join(["?"] * len(insert_cols))
            cur.execute(
                f"INSERT INTO ZCALLRECORD ({', '.join(insert_cols)}) VALUES ({placeholders})",
                [candidate[c] for c in insert_cols],
            )
            cur.execute("UPDATE Z_PRIMARYKEY SET Z_MAX = ? WHERE Z_NAME='CallRecord'", (next_pk,))
            conn.commit()
            log("ok", f"row pk={next_pk} number={number} dir={direction} answered={bool(answered)}")
        finally:
            conn.close()


    async def _flow_insert(udid: str, params: dict) -> None:
        scratch = Path(tempfile.mkdtemp(prefix="callhist-"))
        log("info", f"[1/3] snapshotting {DB_DIR} …")
        local = await _snapshot_db(udid, scratch)
        if local is None:
            die("airlift read failed"); return
        try:
            log("info", "[2/3] mutating local sqlite copy …")
            _checkpoint_wal(local)
            _mutate_sqlite(local, params)
            _checkpoint_wal(local)
        except Exception as e:
            die(f"sqlite mutate failed: {e}"); return
        if not _push_db(udid, local):
            die("airlift write-back failed"); return
        emit("result", ok=True, exit_code=0, wrote=str(local))


    async def _flow_snapshot(udid: str) -> None:
        scratch = Path(tempfile.mkdtemp(prefix="callhist-"))
        local = await _snapshot_db(udid, scratch)
        if local is None:
            die("airlift read failed"); return
        emit("result", ok=True, exit_code=0, saved_to=str(local.parent))


    def run(params: dict) -> None:
        udid = params.get("udid")
        action = params.get("action", "insert")
        if not udid:
            die("missing udid"); return
        try:
            if action == "insert":
                asyncio.run(_flow_insert(udid, params)); return
            if action == "snapshot":
                asyncio.run(_flow_snapshot(udid)); return
            die(f"unknown action: {action}")
        except Exception as e:
            import traceback
            die(f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=8))


if __name__ == "__main__":
    try:
        params = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        die(f"bad stdin json: {e}"); sys.exit(1)
    run(params)
