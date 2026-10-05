 

import os
import time
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/blockchain", tags=["blockchain"])

 
_anchor_svc = None


def set_anchor_service(svc):
    """Called by main.py to inject the AnchorService instance."""
    global _anchor_svc
    _anchor_svc = svc


# Models  

class ProofVerifyRequest(BaseModel):
    artifact_id: str
    sha256: str


#   Routes  

@router.get("/status", summary="Blockchain anchor status")
def blockchain_status():
    """
    Returns current blockchain anchor status including:
    - Network info
    - Wallet address
    - Last anchor TX
    - Pending artifact count
    - Total anchored count
    """
    from blockchain.scheduler import get_pending_count, get_last_anchor_info
    from database import get_db

    db = get_db()
    total_row = db.execute("SELECT COUNT(*) as cnt FROM artifacts").fetchone()
    anchored_row = db.execute(
        "SELECT COUNT(*) as cnt FROM artifacts WHERE ledger_tx IS NOT NULL"
    ).fetchone()
    db.close()

    total = total_row["cnt"] if total_row else 0
    anchored = anchored_row["cnt"] if anchored_row else 0
    pending = get_pending_count()
    last = get_last_anchor_info()

    enabled = _anchor_svc.enabled if _anchor_svc else False
    wallet = _anchor_svc.wallet_address() if _anchor_svc else None
    chain_id = _anchor_svc.chain_id() if _anchor_svc else None

    # Map known chain IDs to human-readable names
    chain_names = {
        80002: "Polygon Amoy Testnet",
        137:   "Polygon Mainnet",
        1:     "Ethereum Mainnet",
        11155111: "Ethereum Sepolia Testnet",
    }
    network_name = chain_names.get(chain_id, f"Chain ID {chain_id}") if chain_id else "Unknown"

    return {
        "blockchain_enabled": enabled,
        "network": network_name,
        "chain_id": chain_id,
        "contract_address": os.environ.get("CONTRACT_ADDRESS"),
        "wallet_address": wallet,
        "explorer_base_url": "https://amoy.polygonscan.com/tx/",
        "anchor_interval_seconds": int(os.environ.get("ANCHOR_INTERVAL_SECONDS", "60")),
        "total_artifacts": total,
        "total_anchored": anchored,
        "pending_anchor": pending,
        "last_anchor": last or None,
    }


@router.get("/verify-proof/{artifact_id}", summary="Verify Merkle proof for an artifact")
def verify_merkle_proof(artifact_id: str):
    """
    Verifies that the stored Merkle proof for an artifact is mathematically valid.

    This is a local (off-chain) cryptographic check — it proves the artifact's
    SHA-256 hash was included in the Merkle root that was anchored on-chain.

    Response:
        {
          "valid": true,
          "artifact_id": "...",
          "sha256": "...",
          "merkle_root": "...",
          "ledger_tx": "0x...",
          "explorer_url": "https://amoy.polygonscan.com/tx/0x..."
        }
    """
    from blockchain.merkle import verify_proof
    from database import get_db
    import json

    db = get_db()
    row = db.execute(
        "SELECT id, sha256, merkle_root, merkle_proof, ledger_tx FROM artifacts WHERE id=?",
        (artifact_id,)
    ).fetchone()
    db.close()

    if not row:
        raise HTTPException(404, f"Artifact {artifact_id!r} not found")

    if not row["merkle_root"]:
        return {
            "valid": False,
            "artifact_id": artifact_id,
            "reason": "Artifact has not been anchored yet. Try again after the next anchor cycle.",
        }

    proof = json.loads(row["merkle_proof"]) if row["merkle_proof"] else []
    is_valid = verify_proof(
        leaf=row["sha256"],
        proof=proof,
        root=row["merkle_root"],
    )

    ledger_tx = row["ledger_tx"]
    return {
        "valid": is_valid,
        "artifact_id": artifact_id,
        "sha256": row["sha256"],
        "merkle_root": row["merkle_root"],
        "merkle_proof": proof,
        "ledger_tx": ledger_tx,
        "explorer_url": (
            f"https://amoy.polygonscan.com/tx/{ledger_tx}" if ledger_tx else None
        ),
    }


@router.post("/trigger-anchor", summary="Manually trigger an anchor cycle (admin)")
def manual_anchor(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Immediately runs an anchor cycle without waiting for the next scheduled interval.
    Requires a valid API key — admin only.
    """
    from database import get_db as _get_db
    from fastapi import HTTPException as _HTTPException
    db = _get_db()
    row = db.execute(
        "SELECT owner FROM api_keys WHERE key=? AND active=1", (x_api_key,)
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(401, "Invalid or inactive API key")

    from blockchain.scheduler import _anchor_job
    try:
        _anchor_job()
        return {"ok": True, "message": "Anchor cycle triggered manually"}
    except Exception as exc:
        raise HTTPException(500, f"Anchor cycle failed: {exc}")
