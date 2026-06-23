"""
Finds swap chains (cycles) among "who-gives-what-to-whom" edges.

A swap chain is a loop where goods circulate and everyone gives exactly one item
and receives exactly one item:

    direct (2-way):   A --book--> B,  B --jacket--> A
    triangular (3-way): A --book--> C,  C --headphones--> B,  B --jacket--> A

The edges come from wishlist matches: a match "user W wants listing L" means
L's owner can GIVE L to W. So one edge = (from_user=listing owner, to_user=wanter,
listing_id, category). A cycle over these edges is a valid swap.

This module is pure logic - it takes edges in and returns chains out. It does NOT
touch the database. Reading wishlist_matches / listing owners to build the edges,
and writing swap_chains/swap_legs from a found chain, happen in the API layer.

Chains are capped at length 3 on purpose: longer chains rarely close (every
participant must accept) and are fragile to execute.
"""

from collections import defaultdict
from dataclasses import dataclass

MAX_CHAIN_LENGTH = 3


@dataclass(frozen=True)
class SwapEdge:
    """One item moving: from_user GIVES listing_id to to_user (who wanted it)."""
    from_user: str
    to_user: str
    listing_id: str
    category: str


@dataclass(frozen=True)
class SwapChain:
    """A closed loop of legs. legs[i].to_user == legs[i+1].from_user, and it wraps."""
    legs: tuple[SwapEdge, ...]

    @property
    def length(self) -> int:
        return len(self.legs)

    @property
    def participants(self) -> set[str]:
        return {leg.from_user for leg in self.legs}


def _canonical_key(legs: list[SwapEdge]) -> tuple:
    """
    A loop found starting from A, B, or C is the same chain. Rotate so it always
    starts at the smallest from_user, giving every rotation an identical key for
    deduplication.
    """
    n = len(legs)
    start = min(range(n), key=lambda i: legs[i].from_user)
    rotated = legs[start:] + legs[:start]
    return tuple((leg.from_user, leg.to_user, leg.listing_id) for leg in rotated)


def _is_valid_loop(legs: list[SwapEdge]) -> bool:
    """A real swap: every participant gives once and receives once, distinct items."""
    givers = [leg.from_user for leg in legs]
    receivers = [leg.to_user for leg in legs]
    listings = [leg.listing_id for leg in legs]
    return (
        len(set(givers)) == len(givers)          # each user gives at most once
        and len(set(receivers)) == len(receivers)  # each user receives at most once
        and len(set(listings)) == len(listings)    # no item moves twice
    )


def find_swap_chains(edges: list[SwapEdge], max_length: int = MAX_CHAIN_LENGTH) -> list[SwapChain]:
    """
    Return all distinct swap chains (2-way up to max_length) found in `edges`.

    Each returned SwapChain is a closed loop; record its legs as swap_legs and the
    chain itself as a swap_chains row.
    """
    # adjacency: from_user -> its outgoing edges
    out_edges: dict[str, list[SwapEdge]] = defaultdict(list)
    for edge in edges:
        if edge.from_user != edge.to_user:  # ignore any accidental self-edges
            out_edges[edge.from_user].append(edge)

    found: dict[tuple, SwapChain] = {}

    def record(legs: list[SwapEdge]) -> None:
        if not _is_valid_loop(legs):
            return
        found[_canonical_key(legs)] = SwapChain(legs=tuple(legs))

    for e1 in edges:                                   # A -> B
        a, b = e1.from_user, e1.to_user
        for e2 in out_edges.get(b, []):                # B -> C
            c = e2.to_user
            if c == a:
                record([e1, e2])                       # 2-way: A -> B -> A
                continue
            if max_length >= 3:
                for e3 in out_edges.get(c, []):        # C -> ?
                    if e3.to_user == a:
                        record([e1, e2, e3])           # 3-way: A -> B -> C -> A

    return list(found.values())


if __name__ == "__main__":
    # Demo (pure Python, no DB): the Alice/Bob/Carol triangle.
    #   Alice has book, wants jacket
    #   Bob   has jacket, wants headphones
    #   Carol has headphones, wants book
    # Goods-flow edges (giver --item--> receiver):
    demo_edges = [
        SwapEdge(from_user="alice", to_user="carol", listing_id="book", category="books"),
        SwapEdge(from_user="carol", to_user="bob", listing_id="headphones", category="electronics"),
        SwapEdge(from_user="bob", to_user="alice", listing_id="jacket", category="clothes"),
        # a dangling edge that forms no loop:
        SwapEdge(from_user="dave", to_user="alice", listing_id="lamp", category="other"),
    ]

    chains = find_swap_chains(demo_edges)
    print(f"Found {len(chains)} chain(s):")
    for chain in chains:
        path = " -> ".join(f"{leg.from_user}({leg.listing_id})" for leg in chain.legs)
        print(f"  [{chain.length}-way] {path} -> back to {chain.legs[0].from_user}")
