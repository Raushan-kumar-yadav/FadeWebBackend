 
import json
import logging
import os
import time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from blockchain.anchor import AnchorService
from blockchain.merkle import build_merkle_tree
from database import get_db

logger = logging.getLogger(__name__)

# Singleton instances  
_scheduler: Optional[BackgroundScheduler] = None
_anchor_svc: Optional[AnchorService] = None


#   Core job  

def _anchor_job():
     
    global _anchor_svc

    if _anchor_svc is None:
        return

    db = None
    try:
        db = get_db()

        #  Find all artifacts not yet anchored
        rows = db.execute(
            "SELECT id, sha256 FROM artifacts WHERE ledger_tx IS NULL ORDER BY registered_at ASC"
        ).fetchall()

        if not rows:
            logger.debug("[Scheduler] No pending artifacts to anchor.")
            return

        ids = [r["id"] for r in rows]
        hashes = [r["sha256"] for r in rows]
        batch_size = len(ids)

        logger.info("[Scheduler] Anchoring batch of %d artifacts…", batch_size)

        #  Build Merkle tree
        tree = build_merkle_tree(hashes)
        root = tree["root"]
        proofs = tree["proofs"]

        #  Anchor root on-chain
        tx_hash = _anchor_svc.anchor_root(merkle_root=root, batch_size=batch_size)

        if tx_hash is None and _anchor_svc.enabled:
            # Anchoring failed 
            logger.warning("[Scheduler] Anchoring failed. Will retry next cycle.")
            return

 
 
        now = int(time.time())

        #  Update each artifact with its proof + root + tx
        for artifact_id, sha256_hex in zip(ids, hashes):
            proof_path = proofs.get(sha256_hex, [])
            db.execute(
                """UPDATE artifacts
                   SET merkle_root=?, merkle_proof=?, ledger_tx=?, anchored_at=?
                   WHERE id=?""",
                (
                    root,
                    json.dumps(proof_path),
                    tx_hash,       # None if blockchain disabled
                    now,
                    artifact_id,
                ),
            )

        db.commit()

        if tx_hash:
            logger.info(
                "[Scheduler] ✅ Batch anchored | root=%s… | tx=%s | count=%d",
                root[:16],
                tx_hash,
                batch_size,
            )
        else:
            logger.info(
                "[Scheduler] Merkle root computed (blockchain disabled) | root=%s… | count=%d",
                root[:16],
                batch_size,
            )

    except Exception as exc:
        logger.exception("[Scheduler] _anchor_job crashed: %s", exc)
    finally:
        if db:
            db.close()


# Public API  

def start_scheduler(anchor_service: AnchorService):
     
    global _scheduler, _anchor_svc

    _anchor_svc = anchor_service

    interval_seconds = int(os.environ.get("ANCHOR_INTERVAL_SECONDS", "60"))

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _anchor_job,
        trigger="interval",
        seconds=interval_seconds,
        id="anchor_job",
        max_instances=1,      # never run two at once
        coalesce=True,
        replace_existing=True,
    )
    _scheduler.start()

    logger.info(
        "[Scheduler] Blockchain anchor job started (interval=%ds, blockchain_enabled=%s)",
        interval_seconds,
        anchor_service.enabled,
    )


def stop_scheduler():
    """Gracefully shut down the scheduler. Call from FastAPI shutdown event."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")


def get_pending_count() -> int:
    """Return the number of artifacts not yet anchored on-chain."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM artifacts WHERE ledger_tx IS NULL"
        ).fetchone()
        db.close()
        return row["cnt"] if row else 0
    except Exception:
        return -1


def get_last_anchor_info() -> dict:
    """Return info about the most recently anchored artifact."""
    try:
        db = get_db()
        row = db.execute(
            """SELECT ledger_tx, merkle_root, anchored_at
               FROM artifacts
               WHERE ledger_tx IS NOT NULL
               ORDER BY anchored_at DESC
               LIMIT 1"""
        ).fetchone()
        db.close()
        if row:
            return {
                "ledger_tx": row["ledger_tx"],
                "merkle_root": row["merkle_root"],
                "anchored_at": row["anchored_at"],
            }
        return {}
    except Exception:
        return {}
