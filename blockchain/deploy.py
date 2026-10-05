"""
Deploy FadeAnchor.sol to Polygon Amoy Testnet.
Run once — prints the contract address.
"""
import json, pathlib, time
from solcx import compile_source, set_solc_version
from web3 import Web3

# ── Config ───────────────────────────────────────────────
PRIVATE_KEY  = "0x362054ab5c184b41db5b477bfad0b45900a24ab0f5d49657a78dbd5acfb6541e"
RPC_URL      = "https://polygon-amoy-bor-rpc.publicnode.com"
SOL_FILE     = pathlib.Path(__file__).parent / "contract.sol"

# ── Connect ──────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
assert w3.is_connected(), "Cannot connect to RPC"
account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"Deploying from : {account.address}")
print(f"Balance        : {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} POL")

# ── Compile ──────────────────────────────────────────────
set_solc_version("0.8.20")
source = SOL_FILE.read_text()
compiled = compile_source(source, output_values=["abi", "bin"])
contract_id = [k for k in compiled if "FadeAnchor" in k][0]
abi      = compiled[contract_id]["abi"]
bytecode = compiled[contract_id]["bin"]
print(f"Compiled       : {len(bytecode)//2} bytes")

# ── Deploy ───────────────────────────────────────────────
Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
nonce    = w3.eth.get_transaction_count(account.address)
tx = Contract.constructor().build_transaction({
    "from":     account.address,
    "nonce":    nonce,
    "gas":      1_200_000,
    "gasPrice": w3.to_wei("30", "gwei"),
    "chainId":  80002,   # Polygon Amoy
})
signed = account.sign_transaction(tx)
print("Sending deployment tx...")
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"TX hash        : {tx_hash.hex()}")
print("Waiting for confirmation (~15s)...")
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
contract_address = receipt["contractAddress"]
print(f"\n✅ Contract deployed!")
print(f"CONTRACT_ADDRESS={contract_address}")
print(f"TX hash: https://amoy.polygonscan.com/tx/{tx_hash.hex()}")

# ── Save ABI ─────────────────────────────────────────────
abi_path = pathlib.Path(__file__).parent / "abi.json"
abi_path.write_text(json.dumps(abi, indent=2))
print(f"ABI saved to {abi_path}")
