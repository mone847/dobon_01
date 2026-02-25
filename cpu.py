# CPUのアルゴリズム
from typing import Callable, Optional

def rank_of(card_id: int) -> int:
    # 1..13
    return ((card_id - 1) % 13) + 1

def choose_card_lv1(hand: list[int], field: int, can_play: Callable[[int, int], bool]) -> Optional[int]:
    playable = [c for c in hand if can_play(c, field)]
    if not playable:
        return None
    # 数が大きい順（rank大きい＝優先）
    playable.sort(key=lambda c: rank_of(c), reverse=True)
    return playable[0]

def rank_of(card_id: int) -> int:
    return ((card_id - 1) % 13) + 1

def suit_of(card_id: int) -> int:
    return (card_id - 1) // 13  # 0..3

def find_protect_cards(hand: list[int], target: int) -> set[int]:
    """
    温存すべきカード集合を返す
    - 同じ数字ペア
    - 2枚和が target になるペア
    """
    protect = set()

    from collections import defaultdict
    by_rank = defaultdict(list)
    for c in hand:
        by_rank[rank_of(c)].append(c)

    # 同ランクペア
    for r, cards in by_rank.items():
        if len(cards) >= 2:
            protect.update(cards)

    # target になる2枚和ペア
    n = len(hand)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = hand[i], hand[j]
            if rank_of(a) + rank_of(b) == target:
                protect.add(a)
                protect.add(b)

    return protect

def choose_card_lv2(hand: list[int], field: int, can_play):
    if field is None:
        return None

    field_rank = rank_of(field)
    field_suit = suit_of(field)

    playable = [c for c in hand if can_play(c, field)]
    if not playable:
        return None

    protect = find_protect_cards(hand, field_rank)

    # ① 温存以外
    non_protect = [c for c in playable if c not in protect]

    # ② さらに「場を動かさない」カード
    # ＝ 同じ数字を出す（rankが同じ）
    same_rank = [c for c in non_protect if rank_of(c) == field_rank]

    if same_rank:
        same_rank.sort(key=lambda c: rank_of(c), reverse=True)
        return same_rank[0]

    # ③ 温存以外から最大rank
    if non_protect:
        non_protect.sort(key=lambda c: rank_of(c), reverse=True)
        return non_protect[0]

    # ④ 仕方なく温存カードから
    playable.sort(key=lambda c: rank_of(c), reverse=True)
    return playable[0]