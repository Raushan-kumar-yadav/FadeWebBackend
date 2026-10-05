import hashlib
from typing import List, Dict, Any


def _hash_pair(left: str, right: str) -> str:
    """SHA-256 of sorted(left, right) concatenated — Ethereum Merkle convention."""
    a, b = (left, right) if left <= right else (right, left)
    combined = bytes.fromhex(a) + bytes.fromhex(b)
    return hashlib.sha256(combined).hexdigest()


def build_merkle_tree(leaves: List[str]) -> Dict[str, Any]:
    """
    Build a Merkle tree from a list of SHA-256 hex strings.

    Returns:
        {
            "root":   "64-char hex Merkle root",
            "layers": [[padded_leaf0, ...], [level1_hash0, ...], ...],
            "proofs": { "leaf_hex": ["sibling0_hex", ...], ... }
        }
    """
    if not leaves:
        raise ValueError("Cannot build a Merkle tree with zero leaves")

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for leaf in leaves:
        low = leaf.lower()
        if low not in seen:
            seen.add(low)
            unique.append(low)
    leaves = unique

    # Single-leaf edge case
    if len(leaves) == 1:
        return {
            "root": leaves[0],
            "layers": [leaves[:]],
            "proofs": {leaves[0]: []},
        }

    # Build layers  
    padded_layers: List[List[str]] = []
    current = leaves[:]

    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])   # pad with duplicate of last
        padded_layers.append(current[:])  # store padded layer for proof use
        next_layer = [
            _hash_pair(current[i], current[i + 1])
            for i in range(0, len(current), 2)
        ]
        current = next_layer

    root = current[0]

    # Build proof path for each leaf
    proofs: Dict[str, List[str]] = {}
    for leaf_idx, leaf in enumerate(leaves):
        proof: List[str] = []
        idx = leaf_idx
        for layer in padded_layers:
            sibling_idx = idx + 1 if idx % 2 == 0 else idx - 1
            proof.append(layer[sibling_idx])
            idx //= 2
        proofs[leaf] = proof

    return {
        "root": root,
        "layers": padded_layers,
        "proofs": proofs,
    }


def verify_proof(leaf: str, proof: List[str], root: str) -> bool:
    """
    Verify that a leaf is part of a Merkle tree with the given root.

    Args:
        leaf:  64-char hex sha256 of the artifact
        proof: list of sibling hashes from build_merkle_tree()["proofs"][leaf]
        root:  expected Merkle root

    Returns:
        True if the proof is valid, False otherwise.
    """
    computed = leaf.lower()
    for sibling in proof:
        computed = _hash_pair(computed, sibling.lower())
    return computed == root.lower()
