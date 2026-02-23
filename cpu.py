# CPUのアルゴリズム

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