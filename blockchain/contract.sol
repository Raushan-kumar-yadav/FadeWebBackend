// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FadeAnchor
 * @notice Stores Merkle roots of Fade artifact proof bundles on-chain.
 *         Each root represents a batch of artifact SHA-256 hashes.
 *         Deployed on Polygon Amoy Testnet (free for SIH demo).
 *
 * @dev Deploy via Remix IDE (https://remix.ethereum.org):
 *      1. Compile with Solidity 0.8.20
 *      2. Connect MetaMask to Polygon Amoy Testnet
 *      3. Deploy — copy the contract address into .env
 */
contract FadeAnchor {
    //   State  

    address public owner;

    // root hex string  →  block timestamp when it was anchored
    mapping(string => uint256) public rootTimestamps;

    // Ordered list of all anchored roots (for enumeration)
    string[] public roots;
 
    //   Events  

    /**
     * @param root Merkle root hex string (64 chars)
     * @param anchoredAt Block timestamp
     * @param batchSize  Number of artifacts in this batch
     */
    event RootAnchored(string root, uint256 anchoredAt, uint256 batchSize);

    // Modifiers  

    modifier onlyOwner() {
        require(msg.sender == owner, "FadeAnchor: caller is not owner");
        _;
    }

    // Constructor  

    constructor() {
        owner = msg.sender;
    }

    //   Functions  

    /**
     * @notice Anchor a Merkle root representing a batch of artifact hashes.
     * @param root       64-char hex Merkle root
     * @param batchSize  How many artifacts are in this batch (for transparency)
     */
    function storeRoot(string calldata root, uint256 batchSize) external onlyOwner {
        require(bytes(root).length == 64, "FadeAnchor: root must be 64 hex chars");
        require(rootTimestamps[root] == 0, "FadeAnchor: root already anchored");

        rootTimestamps[root] = block.timestamp;
        roots.push(root);

        emit RootAnchored(root, block.timestamp, batchSize);
    }

    /**
     * @notice Check if a Merkle root has been anchored on-chain.
     * @param root  64-char hex Merkle root to look up
     * @return      True if anchored, false otherwise
     */
    function isRootAnchored(string calldata root) external view returns (bool) {
        return rootTimestamps[root] != 0;
    }

    /**
     * @notice Return the timestamp when a root was anchored (0 = not anchored).
     */
    function getRootTimestamp(string calldata root) external view returns (uint256) {
        return rootTimestamps[root];
    }

    /**
     * @notice Total number of anchored batches.
     */
    function totalRoots() external view returns (uint256) {
        return roots.length;
    }

    /**
     * @notice Transfer ownership (to rotate wallet).
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "FadeAnchor: zero address");
        owner = newOwner;
    }
}
