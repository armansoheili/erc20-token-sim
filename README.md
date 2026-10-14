# erc20-token-sim

A faithful, dependency-free **ERC-20 token ledger simulator** in pure Python.

Models the exact [EIP-20](https://eips.ethereum.org/EIPS/eip-20) interface semantics — `totalSupply`, `balanceOf`, `transfer`, `approve`, `allowance`, `transferFrom` — plus owner-only `mint`/`burn`, race-safe allowance helpers (`increaseAllowance` / `decreaseAllowance` semantics), and an in-memory event log of every `Transfer`/`Approval`.

All amounts are integers (token "atoms" = value × 10^decimals), exactly like on-chain math.

## Usage

```python
from erc20 import ERC20Token

t = ERC20Token("My Token", "MTK", decimals=18,
               supply=1_000_000 * 10**18, owner="deployer")

t.transfer("deployer", "alice", t.atoms(1000))
t.approve("alice", "bob", t.atoms(250))
t.transfer_from("bob", "alice", "carol", t.atoms(250))  # spends allowance first
t.mint("deployer", "dave", t.atoms(500))                # owner only
t.burn("alice", t.atoms(100))                           # supply shrinks

assert t.check_invariant()  # totalSupply == sum of all balances, always
```

Run the demo: `python erc20.py` · run the doctests: `python erc20.py --test`

## Notes

- `transferFrom` spends the allowance **before** moving funds, so a failed transfer (insufficient balance) never consumes allowance — matching contract behavior.
- Setting a non-zero allowance directly is subject to the classic approve race; `increase_allowance` / `decrease_allowance` avoid it.
- Zero-address transfers and negative amounts raise; unknown accounts simply have balance 0.
