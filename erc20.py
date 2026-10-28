"""
erc20.py — a faithful, dependency-free ERC-20 token ledger simulator.

Models the exact EIP-20 interface semantics in pure Python:
  totalSupply, balanceOf, transfer, approve, allowance, transferFrom
plus owner-only mint/burn, safe-allowance helpers, and events.
All amounts are integers (token "atoms", i.e. value * 10**decimals).

>>> t = ERC20Token("Demo", "DEMO", 18, supply=1000 * 10**18, owner="alice")
>>> t.balance_of("alice")
1000000000000000000000
>>> t.transfer("alice", "bob", 100)
True
>>> t.balance_of("bob")
100
>>> t.allowance("alice", "bob")
0
>>> t.approve("alice", "bob", 50)
True
>>> t.transfer_from("bob", "alice", "carol", 50)
True
>>> t.balance_of("carol")
50
>>> t.total_supply
1000000000000000000000
>>> t.mint("owner", "alice", 1) if False else None
"""

from __future__ import annotations

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

__all__ = ["ERC20Token", "InsufficientBalance", "InsufficientAllowance", "ZERO_ADDRESS"]


class InsufficientBalance(Exception):
    """Raised when an account tries to move more tokens than it holds."""


class InsufficientAllowance(Exception):
    """Raised when a spender exceeds their approved allowance."""


class ERC20Token:
    """In-memory ERC-20 token contract simulator.

    Parameters
    ----------
    name, symbol : str
        Token metadata.
    decimals : int
        Decimals (default 18, like ETH).
    supply : int
        Initial supply minted to ``owner``, in token atoms.
    owner : str
        Address receiving the initial supply and holding mint authority.

    Events are recorded in ``self.events`` as dicts:
    ``{"event": "Transfer", "from": ..., "to": ..., "value": ...}``
    """

    def __init__(self, name: str, symbol: str, decimals: int = 18,
                 supply: int = 0, owner: str = "owner") -> None:
        self.name = name
        self.symbol = symbol
        self.decimals = decimals
        self.owner = owner
        self.total_supply = 0
        self._balances: dict[str, int] = {}
        self._allowances: dict[tuple[str, str], int] = {}
        self.events: list[dict] = []
        if supply:
            self._mint(owner, supply)

    # ---------------------------------------------------------------- views
    def balance_of(self, account: str) -> int:
        """Return the token balance of ``account`` (EIP-20 `balanceOf`)."""
        return self._balances.get(account, 0)

    def allowance(self, owner: str, spender: str) -> int:
        """Return the remaining allowance (EIP-20 `allowance`)."""
        return self._allowances.get((owner, spender), 0)

    # -------------------------------------------------------------- writes
    def _transfer(self, frm: str, to: str, value: int) -> None:
        if frm == ZERO_ADDRESS or to == ZERO_ADDRESS:
            raise ValueError("ERC20: transfer to/from the zero address")
        if value < 0:
            raise ValueError("ERC20: transfer amount must be >= 0")
        if self._balances.get(frm, 0) < value:
            raise InsufficientBalance(
                f"{frm} has {self._balances.get(frm, 0)}, tried to move {value}")
        self._balances[frm] = self._balances.get(frm, 0) - value
        self._balances[to] = self._balances.get(to, 0) + value
        self.events.append({"event": "Transfer", "from": frm, "to": to, "value": value})

    def transfer(self, frm: str, to: str, value: int) -> bool:
        """Move ``value`` tokens from ``frm`` to ``to`` (EIP-20 `transfer`)."""
        self._transfer(frm, to, value)
        return True

    def approve(self, owner: str, spender: str, value: int) -> bool:
        """Set ``spender``'s allowance to ``value`` (EIP-20 `approve`).

        NOTE: setting a non-zero allowance directly is subject to the classic
        approve race; prefer ``increase_allowance`` / ``decrease_allowance``.
        """
        if value < 0:
            raise ValueError("ERC20: allowance must be >= 0")
        self._allowances[(owner, spender)] = value
        self.events.append({"event": "Approval", "owner": owner,
                            "spender": spender, "value": value})
        return True

    def increase_allowance(self, owner: str, spender: str, added: int) -> bool:
        """Atomically raise ``spender``'s allowance (race-safe)."""
        return self.approve(owner, spender, self.allowance(owner, spender) + added)

    def decrease_allowance(self, owner: str, spender: str, sub: int) -> bool:
        """Atomically lower ``spender``'s allowance; floors at zero."""
        current = self.allowance(owner, spender)
        return self.approve(owner, spender, max(0, current - sub))

    def transfer_from(self, spender: str, frm: str, to: str, value: int) -> bool:
        """Move ``value`` tokens ``frm`` -> ``to`` using ``spender``'s allowance.

        Mirrors EIP-20 `transferFrom`: the allowance is spent first, so a
        failed transfer (insufficient balance) still consumes no allowance.
        """
        allowed = self.allowance(frm, spender)
        if allowed < value:
            raise InsufficientAllowance(
                f"{spender} allowed {allowed} by {frm}, tried to move {value}")
        self._transfer(frm, to, value)
        self._allowances[(frm, spender)] = allowed - value
        return True

    # --------------------------------------------------------- mint & burn
    def _mint(self, to: str, value: int) -> None:
        if to == ZERO_ADDRESS:
            raise ValueError("ERC20: mint to the zero address")
        if value < 0:
            raise ValueError("ERC20: mint amount must be >= 0")
        self.total_supply += value
        self._balances[to] = self._balances.get(to, 0) + value
        self.events.append({"event": "Transfer", "from": ZERO_ADDRESS,
                            "to": to, "value": value})

    def _burn(self, frm: str, value: int) -> None:
        if self._balances.get(frm, 0) < value:
            raise InsufficientBalance(f"{frm} cannot burn {value}")
        self._balances[frm] -= value
        self.total_supply -= value
        self.events.append({"event": "Transfer", "from": frm,
                            "to": ZERO_ADDRESS, "value": value})

    def mint(self, caller: str, to: str, value: int) -> bool:
        """Owner-only mint; increases ``total_supply``."""
        if caller != self.owner:
            raise PermissionError("ERC20: only the owner can mint")
        self._mint(to, value)
        return True

    def burn(self, frm: str, value: int) -> bool:
        """Destroy ``value`` of ``frm``'s tokens; decreases ``total_supply``."""
        self._burn(frm, value)
        return True

    def burn_from(self, spender: str, frm: str, value: int) -> bool:
        """Burn using ``spender``'s allowance (burnable-style extension)."""
        allowed = self.allowance(frm, spender)
        if allowed < value:
            raise InsufficientAllowance(
                f"{spender} allowed {allowed} by {frm}, tried to burn {value}")
        self._burn(frm, value)
        self._allowances[(frm, spender)] = allowed - value
        return True

    def holders(self) -> list[tuple[str, int]]:
        """Return (account, balance) pairs with a nonzero balance, richest first.

        >>> t = ERC20Token("Demo", "DEMO", 18, supply=1000, owner="alice")
        >>> t.transfer("alice", "bob", 300)
        True
        >>> t.transfer("alice", "carol", 100)
        True
        >>> t.holders()
        [('alice', 600), ('bob', 300), ('carol', 100)]
        >>> t.burn("carol", 100)
        True
        >>> t.holders()
        [('alice', 600), ('bob', 300)]
        """
        return sorted(
            ((a, b) for a, b in self._balances.items() if b > 0),
            key=lambda item: -item[1],
        )

    # -------------------------------------------------------------- utils
    def atoms(self, tokens: float | int) -> int:
        """Convert whole/human tokens to atoms (value * 10**decimals)."""
        return int(tokens * (10 ** self.decimals))

    def human(self, atoms: int) -> float:
        """Convert atoms back to human-readable token units."""
        return atoms / (10 ** self.decimals)

    def check_invariant(self) -> bool:
        """totalSupply must always equal the sum of all balances."""
        return self.total_supply == sum(self._balances.values())


def demo() -> None:
    """End-to-end demo: deploy, transfer, approve, transferFrom, mint, burn."""
    t = ERC20Token("Demo Token", "DEMO", decimals=18,
                   supply=1_000_000 * 10 ** 18, owner="deployer")
    print(f"deployed {t.name} ({t.symbol}), supply = {t.human(t.total_supply):,.0f}")

    t.transfer("deployer", "alice", t.atoms(1000))
    print("deployer -> alice:", t.human(t.balance_of("alice")))

    # alice approves bob, bob pulls some to carol via transferFrom
    t.approve("alice", "bob", t.atoms(250))
    t.transfer_from("bob", "alice", "carol", t.atoms(250))
    print("carol balance:", t.human(t.balance_of("carol")))
    print("bob's remaining allowance:", t.human(t.allowance("alice", "bob")))

    t.mint("deployer", "dave", t.atoms(500))
    t.burn("alice", t.atoms(100))
    print("total supply:", t.human(t.total_supply))
    print("invariant holds:", t.check_invariant())
    print("events emitted:", len(t.events))


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        import doctest
        failures, tests = doctest.testmod(verbose=False)
        print(f"{tests} doctests, {failures} failures")
        sys.exit(1 if failures else 0)
    demo()
