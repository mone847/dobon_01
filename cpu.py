# CPUの思考ロジック（レベル別）

def rank_of(card_id: int) -> int:
    return ((card_id - 1) % 13) + 1  # 1..13

def suit_of(card_id: int) -> int:
    return (card_id - 1) // 13  # 0..3

def total_rank(hand: list[int]) -> int:
    return sum(rank_of(c) for c in hand)

def count_pairs_by_rank(hand: list[int]) -> int:
    """同じ数字のペア数（例：5が2枚なら1、5が3枚なら1扱いでもOK。ここは“2枚組”で数える）"""
    from collections import Counter
    cnt = Counter(rank_of(c) for c in hand)
    return sum(v // 2 for v in cnt.values())

def has_split_sum_structure(hand: list[int]) -> bool:
    """
    例：7 と (4+3) みたいな “分割” を作りやすい構造があるか（教育的な「ドボン体制」）。
    厳密勝率より「体制を崩さない」方向に効く軽いボーナス。
    """
    ranks = [rank_of(c) for c in hand]
    s = set(ranks)
    for t in range(2, 14):  # 2..13
        # t を (a+b) に分解できるカードがあるか
        for a in range(1, t):
            b = t - a
            if a in s and b in s:
                return True
    return False

def choose_card_lv1(hand: list[int], field: int, can_play: Callable[[int, int], bool]) -> Optional[int]:
    playable = [c for c in hand if can_play(c, field)]
    if not playable:
        return None
    playable.sort(key=lambda c: rank_of(c), reverse=True)
    return playable[0]

def choose_card_lv2(
    hand: list[int],
    field: int,
    can_play: Callable[[int, int], bool],
    *,
    keep_field: bool = False,
) -> Optional[int]:
    """
    lv2（中）: “ドボン圏(合計1..13)に寄せる” + “体制(ペア/分割)を崩しにくい” + “大きいカードを優先して捨てる”
    keep_field=True にすると「場を動かさない」寄り（同じ数字を出す）を強める
    """
    if field is None:
        return None

    playable = [c for c in hand if can_play(c, field)]
    if not playable:
        return None

    field_rank = rank_of(field)

    # 現在の“体制”を把握（これを減らしにくい手を好む）
    base_pairs = count_pairs_by_rank(hand)
    base_split = has_split_sum_structure(hand)
    base_total = total_rank(hand)

    best = None
    best_score = -10**18

    for c in playable:
        new_hand = hand[:]         # shallow copy
        new_hand.remove(c)

        # ルール上、残り1枚は出せない運用があるので、ここでも保険
        if len(new_hand) == 0:
            continue

        new_total = total_rank(new_hand)

        # “体制”変化
        new_pairs = count_pairs_by_rank(new_hand)
        new_split = has_split_sum_structure(new_hand)

        # -------------------------
        # スコア設計（ここがlv2の肝）
        # -------------------------
        score = 0

        # 1) 最重要：合計をドボン圏(1..13)に入れる
        if 1 <= new_total <= 13:
            score += 5000
            # 圏内でも、小さい方が次の調整が効くので少しだけ優遇
            score += (13 - new_total) * 15
        else:
            # 圏外は強烈に罰（大きいほどさらに罰）
            score -= 5000
            score -= (new_total - 13) * 50

        # 2) 大きいカードを切る（合計を下げるのに効く）
        score += rank_of(c) * 30

        # 3) “同ランクペア”を残す（体制維持）
        if new_pairs > base_pairs:
            score += 250
        elif new_pairs < base_pairs:
            score -= 350  # ペアを壊すのは嫌

        # 4) “分割体制”を残す（軽いボーナス）
        if (not base_split) and new_split:
            score += 120
        elif base_split and (not new_split):
            score -= 120

        # 5) 「場を動かさない」版（任意）
        # 同じ数字を出す＝次の人に“合わせやすい”面もあるので、強すぎない加点にしている
        if keep_field and rank_of(c) == field_rank:
            score += 180

        # 6) 追加：合計を下げる方向を好む（現状より合計が減るほど加点）
        score += (base_total - new_total) * 8

        # tie-break：同点なら「より大きいカードを出す」を優先
        if (score > best_score) or (score == best_score and (best is None or rank_of(c) > rank_of(best))):
            best_score = score
            best = c

    return best

def choose_card_lv2_keep_field(hand: list[int], field: int, can_play: Callable[[int, int], bool]) -> Optional[int]:
    """lv2の『場を動かさない』寄り版（要求された別バージョン）"""
    return choose_card_lv2(hand, field, can_play, keep_field=True)