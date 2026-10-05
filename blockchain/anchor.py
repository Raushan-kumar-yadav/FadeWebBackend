 

import json
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Path to the ABI file sitting next to this module
_ABI_PATH = Path(__file__).parent / "abi.json"

# Default public RPC for Polygon Amoy Testnet ( 
_DEFAULT_RPC = "https://rpc-amoy.polygon.technology"


class AnchorService:
    """
    Thin wrapper around web3.py for anchoring Merkle roots to the FadeAnchor
    Smart Contract on Polygon Amoy Testnet.

    Attributes:
        enabled (bool): False when BLOCKCHAIN_ENABLED != "true" or env vars missing.
    """

    def __init__(self):
        self.enabled = os.environ.get("BLOCKCHAIN_ENABLED", "false").lower() == "true"
        self._w3 = None
        self._contract = None
        self._account = None

        if self.enabled:
            self._setup()

    # Setup  

    def _setup(self):
        """Connect to RPC, load contract ABI, prepare account."""
        try:
            from web3 import Web3
            # web3 v7+ moved the POA middleware  
            try:
                from web3.middleware import ExtraDataToPOAMiddleware
            except ImportError:
                from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware
        except ImportError:
            logger.error(
                "[Blockchain] web3 library not installed. "
                "Run: pip install web3>=6.0.0"
            )
            self.enabled = False
            return

        rpc_url = os.environ.get("POLYGON_RPC_URL", _DEFAULT_RPC)
        private_key = os.environ.get("WALLET_PRIVATE_KEY", "")
        contract_address = os.environ.get("CONTRACT_ADDRESS", "")

        if not private_key or not contract_address:
            logger.warning(
                "[Blockchain] WALLET_PRIVATE_KEY or CONTRACT_ADDRESS not set. "
                "Blockchain anchoring disabled."
            )
            self.enabled = False
            return

        # Connect
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Polygon (and most PoS networks) use POA consensus 
         
        self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self._w3.is_connected():
            logger.error("[Blockchain] Cannot connect to RPC: %s", rpc_url)
            self.enabled = False
            return

        # Load account from private key
        self._account = self._w3.eth.account.from_key(private_key)

        # Load contract
        abi = json.loads(_ABI_PATH.read_text())
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi,
        )

        logger.info(
            "[Blockchain] Connected to %s | Wallet: %s | Contract: %s",
            rpc_url,
            self._account.address,
            contract_address,
        )

    # Public API  

    def anchor_root(self, merkle_root: str, batch_size: int) -> Optional[str]:
        """
        Call FadeAnchor.storeRoot(merkle_root, batch_size) on-chain.

        Args:
            merkle_root: 64-char hex Merkle root
            batch_size:  Number of artifacts in this batch

        Returns:
            Transaction hash string ("0x...") on success, None on failure.
        """
        if not self.enabled:
            logger.debug("[Blockchain] Anchoring skipped (disabled)")
            return None

        try:
            from web3 import Web3

            nonce = self._w3.eth.get_transaction_count(self._account.address)

            # Build the transaction
            tx = self._contract.functions.storeRoot(
                merkle_root, batch_size
            ).build_transaction(
                {
                    "from": self._account.address,
                    "nonce": nonce,
                    # Let web3.py estimate gas automatically
                    "gas": 200_000,
                    # Use EIP-1559 pricing (Polygon Amoy supports it)
                    "maxFeePerGas": self._w3.to_wei("30", "gwei"),
                    "maxPriorityFeePerGas": self._w3.to_wei("25", "gwei"),
                    "chainId": self._w3.eth.chain_id,
                }
            )

            # Sign locally  
            signed = self._account.sign_transaction(tx)

            # Broadcast and wait for receipt
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            tx_hex = receipt["transactionHash"].hex()

            if receipt["status"] == 1:
                logger.info(
                    "[Blockchain] ✅ Anchored root=%s  tx=%s  batch=%d",
                    merkle_root[:16] + "...",
                    tx_hex,
                    batch_size,
                )
                return tx_hex
            else:
                logger.error("[Blockchain] ❌ TX reverted: %s", tx_hex)
                return None

        except Exception as exc:
            logger.exception("[Blockchain] anchor_root failed: %s", exc)
            return None

    def is_connected(self) -> bool:
        """Return True if web3 is connected and service is enabled."""
        if not self.enabled or self._w3 is None:
            return False
        return self._w3.is_connected()

    def wallet_address(self) -> Optional[str]:
        """Return the wallet address used for signing, or None."""
        if self._account:
            return self._account.address
        return None

    def chain_id(self) -> Optional[int]:
        """Return the connected chain ID, or None."""
        try:
            return self._w3.eth.chain_id if self._w3 else None
        except Exception:
            return None
