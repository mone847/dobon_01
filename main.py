from js import document, window
import random
import asyncio
from pyodide.ffi import create_proxy

event_proxies = []

# ===== DOM =====
cpuA_title = document.getElementById("cpuA-title")
cpuB_title = document.getElementById("cpuB-title")
cpuC_title = document.getElementById("cpuC-title")
cpuA_cards = document.getElementById("cpuA-cards")
cpuB_cards = document.getElementById("cpuB-cards")
cpuC_cards = document.getElementById("cpuC-cards")

field_img = document.getElementById("field-card")
deck_title = document.getElementById("deck-title")
deck_img = document.getElementById("deck-card")

your_hand = document.getElementById("your-hand")
msg = document.getElementById("msg")
dobon_btn = document.getElementById("dobon-btn")

# ===== cards.js bridge =====
_cards = None

async def ensure_cards():
    global _cards
    if _cards is not None:
        return _cards
    while not hasattr(window, "cards"):
        await asyncio.sleep(0)
    _cards = window.cards
    return _cards

# ===== Game State =====
deck = []       # 山札（残り）
field = None    # 場札（いちばん上1枚）
you = []        # あなたの手札（表で見える）
cpuA = []
cpuB = []
cpuC = []

busy = False

# ---- 重要：カード番号→(スート,数字)の割り当て ----
# c1..c52 の並びを「♣→♦→♥→♠（各A..K）」と仮定。
# もし画像の実並びが違うなら、ここだけ直せばルール判定が合います。
def card_to_suit_rank(i: int):
    suit_index = (i - 1) // 13  # 0..3
    rank = (i - 1) % 13 + 1     # 1..13
    suits = ["C", "D", "H", "S"]  # ♣ ♦ ♥ ♠ のつもり
    return suits[suit_index], rank

def dobon_possible():
    """
    手札すべての合計が
    場札の数字と一致すればドボン可能
    """
    if field is None or len(you) == 0:
        return (False, [])

    target = card_to_suit_rank(field)[1]  # 場の数字
    total = sum(card_to_suit_rank(cid)[1] for cid in you)

    if total == target:
        return (True, you.copy())  # 全部使う
    return (False, [])


def can_play(card_id: int, field_id: int) -> bool:
    s1, r1 = card_to_suit_rank(card_id)
    s2, r2 = card_to_suit_rank(field_id)
    return (s1 == s2) or (r1 == r2)

def has_playable() -> bool:
    if field is None:
        return False
    return any(can_play(c, field) for c in you)

def set_msg(text: str, ok=False, ng=False):
    msg.className = "ok" if ok else ("ng" if ng else "")
    msg.innerText = text

def clear_node(node):
    while node.firstChild:
        node.removeChild(node.firstChild)

def img_el(src: str, cls: str = ""):
    im = document.createElement("img")
    im.src = src
    if cls:
        im.className = cls
    return im

def render_cpu(panel_title_el, panel_cards_el, name: str, cards_list):
    panel_title_el.innerText = f"{name}（{len(cards_list)}枚）"
    clear_node(panel_cards_el)
    # CPUは裏面だけ並べる（枚数分）
    back = _cards.getUrl(0)
    for _ in cards_list:
        panel_cards_el.appendChild(img_el(back))

def render_deck():
    deck_title.innerText = f"山のカード（{len(deck)}枚）"
    deck_img.src = _cards.getUrl(0)

    # ★出せるカードがあるなら山札は引けない
    if len(deck) == 0 or has_playable():
        deck_img.classList.add("disabled")
    else:
        deck_img.classList.remove("disabled")

def render_field():
    if field is None:
        field_img.src = _cards.getUrl(0)
    else:
        field_img.src = _cards.getUrl(field)

def render_hand():
    global event_proxies
    for p in event_proxies:
        try:
            p.destroy()
        except Exception:
            pass
    event_proxies = []

    clear_node(your_hand)

    # まず全カード要素を作る
    card_ids = list(you)

    # コンテナ幅（px）
    w = int(your_hand.clientWidth)
    pad = 28  # paddingぶんの安全マージン
    avail = max(200, w - pad)

    card_w = 140
    gap = 18

    # 通常並びで収まるか？
    n = len(card_ids)
    total_normal = n * card_w + max(0, n - 1) * gap
    use_stack = total_normal > avail

    # 重ね表示のパラメータ（自動調整）
    # 横方向のずらし幅（小さいほど重なる）
    step_x = 34
    # 縦方向のずらし（2段目以降）
    step_y = 42

    # 1行に置ける枚数（重ね表示時）
    if use_stack:
        max_per_row = max(1, int((avail - card_w) // step_x) + 1)
        # 上限を設けたいならここで制限（例：最大18枚/行）
        max_per_row = min(max_per_row, 18)
    else:
        max_per_row = n  # 使わない

    # 高さ見積もり（重ね表示時）
    rows = 1
    if use_stack and n > 0:
        rows = (n + max_per_row - 1) // max_per_row
        # リミッター例：最大3段に制限（それ以上はスクロールで見せる）
        rows = min(rows, 3)

    # コンテナの最低高さを調整
    if use_stack:
        # 240はカード高さに近い値。段が増えたら増やす
        your_hand.style.minHeight = f"{240 + (rows - 1) * step_y}px"
    else:
        your_hand.style.minHeight = "240px"

    # 実配置
    for idx, c in enumerate(card_ids):
        im = img_el(_cards.getUrl(c), "hand-card")
        im.dataset.cardId = str(c)

        # 出せる/出せない表示（判定は維持）
        if field is not None and not can_play(c, field):
            im.classList.add("disabled")

        # クリックで場に出す
        def make_onclick(card_id):
            async def _run():
                await play_card(card_id)

            def _onclick(evt):
                asyncio.create_task(_run())

            return _onclick

        handler = create_proxy(make_onclick(c))
        event_proxies.append(handler)          # ★保持して破棄されないように
        im.addEventListener("click", handler)


        if not use_stack:
            # 通常：流し込み（position指定しない）
            im.style.position = "static"
        else:
            # 重ね表示：絶対配置
            im.classList.add("stack")
            r = idx // max_per_row
            cidx = idx % max_per_row

            # リミッター（3段まで）を超えたら、最後の段に詰める
            if r >= 3:
                r = 2

            left = cidx * step_x
            top = r * step_y
            im.style.left = f"{left}px"
            im.style.top = f"{top}px"
            im.style.zIndex = str(idx)

        your_hand.appendChild(im)


def render_all():
    render_cpu(cpuA_title, cpuA_cards, "プレーヤーA", cpuA)
    render_cpu(cpuB_title, cpuB_cards, "プレーヤーB", cpuB)
    render_cpu(cpuC_title, cpuC_cards, "プレーヤーC", cpuC)
    render_field()
    render_deck()
    render_hand()

# ===== Actions =====
async def reset_async():
    global deck, field, you, cpuA, cpuB, cpuC, busy
    if busy:
        return
    busy = True
    try:
        await ensure_cards()

        # シャッフル
        deck = list(range(1, 53))
        random.shuffle(deck)

        # 5枚ずつ配る
        you = [deck.pop() for _ in range(5)]
        cpuA = [deck.pop() for _ in range(5)]
        cpuB = [deck.pop() for _ in range(5)]
        cpuC = [deck.pop() for _ in range(5)]

        # 場に1枚（表）
        field = deck.pop()

        # 画像初期化（リンク切れ防止）
        field_img.src = _cards.getUrl(field)
        deck_img.src = _cards.getUrl(0)

        set_msg("配布しました。\n同じマーク or 同じ数字のカードをクリックして場に出してください。\n出せるカードが無いときは山札をクリックして1枚取ります。", ok=True)
        render_all()

        # 山札クリック
        def on_deck_click(evt):
            asyncio.create_task(draw_from_deck())

        # 二重登録防止のため、毎回入れ替え
        deck_img.onclick = on_deck_click

    finally:
        busy = False

async def play_card(card_id: int):
    global field, busy
    if busy:
        return
    busy = True
    try:
        if field is None:
            return

        # クリックしたカードが手札に存在しない（タイミング差）対策
        if card_id not in you:
            return

        if not can_play(card_id, field):
            set_msg("そのカードは場に出せません。\n（同じマーク または 同じ数字 ではありません）", ng=True)
            return

        # 場に出す
        you.remove(card_id)
        field = card_id

        # ★念のため場札だけ先に更新（render_allの中でも更新されます）
        render_field()

        set_msg("場に出しました。次の手を選んでください。\n（今回はテストのため、出せても山札を取れます）", ok=True)
        render_all()

    finally:
        busy = False


async def draw_from_deck():
    global busy
    if busy:
        return
    busy = True
    try:
        if len(deck) == 0:
            set_msg("山札がありません。", ng=True)
            return

        # ★出せるカードがあるなら引けない
        if has_playable():
            set_msg("出せるカードがあります。まず手札から場に出してください。", ng=True)
            return

        c = deck.pop()
        you.append(c)
        set_msg("山札から1枚取りました。", ok=True)
        render_all()

    finally:
        busy = False

def card_label(cid: int) -> str:
    s, r = card_to_suit_rank(cid)
    suit_symbol = {"C":"♣","D":"♦","H":"♥","S":"♠"}.get(s, s)
    return f"{suit_symbol}{r}"

def hand_sum(cards):
    return sum(card_to_suit_rank(cid)[1] for cid in cards)

async def try_dobon_async():
    global busy
    if busy:
        return
    busy = True
    try:
        ok, used = dobon_possible()
        target = card_to_suit_rank(field)[1]
        total = sum(card_to_suit_rank(cid)[1] for cid in you)

        if not ok:
            set_msg(
                f"ドボンできません。\n"
                f"手札の合計：{total}\n"
                f"場の数字：{target}",
                ng=True
            )
            return

        # 勝利
        set_msg(
            "ドボン！ あなたの勝ち！\n"
            f"手札の合計：{total} = 場の数字：{target}",
            ok=True
        )

        # 操作停止
        deck_img.classList.add("disabled")
        dobon_btn.disabled = True

    finally:
        busy = False


def try_dobon(event=None):
    asyncio.create_task(try_dobon_async())


# ===== PyScript entry points =====
def reset_game(event=None):
    asyncio.create_task(reset_async())

# init
asyncio.create_task(reset_async())
