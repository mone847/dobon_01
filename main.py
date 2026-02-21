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

selected = None  # iPad向け：選択中カードid（1回目タップで選択）

busy = False

# ---- カード番号→(スート,数字)の割り当て ----
# c1..c52 の並びは「♣→♦→♥→♠（各A..K）」
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
    # ★手札が1枚のときは「ドボン以外では上がれない」ので、出せる扱いにしない
    if field is None:
        return False
    if len(you) <= 1:
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
    # タイトルに枚数を表示
    n = len(cards_list)
    panel_title_el.innerText = f"{name}（{n}枚）"

    clear_node(panel_cards_el)

    if n <= 0:
        panel_cards_el.style.minHeight = "70px"
        return

    back = _cards.getUrl(0)

    # コンテナ幅（0になる環境対策で最低値を入れる）
    w = int(panel_cards_el.clientWidth) if panel_cards_el.clientWidth else 260
    avail = max(120, w - 8)

    # CPUカードは小さめ（CSS側の幅と合わせる）
    card_w = 56 if w < 240 else 52   # 雑に iPad寄りを考慮（必要なら固定でもOK）
    gap = 10

    use_stack = True

    # stack 用パラメータ
    step_x = 18   # 横の重なり（小さいほど “ぎゅっ” と重なる）
    
    base_top = 2 
    panel_cards_el.style.minHeight = "70px"

    for idx in range(n):
        im = img_el(back, "cpu-card")

        if use_stack:
            left = idx * step_x
            top = base_top   # ★常に1段目

            im.classList.add("stack")
            im.style.left = f"{left}px"
            im.style.top = f"{top}px"
            im.style.zIndex = str(idx)

        panel_cards_el.appendChild(im)


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

    # 古い proxy を破棄（クリックが増殖しないように）
    for p in event_proxies:
        try:
            p.destroy()
        except Exception:
            pass
    event_proxies = []

    clear_node(your_hand)

    card_ids = list(you)

    # コンテナ幅
    w = int(your_hand.clientWidth)
    pad = 28
    avail = max(200, w - pad)

    card_w = 140
    gap = 18

    n = len(card_ids)
    total_normal = n * card_w + max(0, n - 1) * gap
    use_stack = total_normal > avail

    # ★上余白：通常/重ねで切替（ホバーで上がっても切れない）
    your_hand.style.paddingTop = "70px" if use_stack else "38px"

    # 重ね表示のパラメータ
    step_x = 34
    step_y = 42
    base_top = 30

    # 1行に置ける枚数（重ね表示時）
    if use_stack:
        max_per_row = max(1, int((avail - card_w) // step_x) + 1)
        max_per_row = min(max_per_row, 18)
    else:
        max_per_row = n if n > 0 else 1

    # 段数（最大3段）
    rows = 1
    if use_stack and n > 0:
        rows = (n + max_per_row - 1) // max_per_row
        rows = min(rows, 3)

    # 高さ確保
    if use_stack:
        your_hand.style.minHeight = f"{260 + (rows - 1) * step_y}px"
    else:
        your_hand.style.minHeight = "240px"

    # 出せる/出せない（表示用）
    playable = set()
    if field is not None:
        for c in you:
            if can_play(c, field):
                playable.add(c)

    for idx, cid in enumerate(card_ids):
        im = img_el(_cards.getUrl(cid), "hand-card")
        im.dataset.cardId = str(cid)

        if selected == cid:
            im.classList.add("selected")

        if field is not None and cid not in playable:
            im.classList.add("disabled")

        # クリック handler（proxyで保持）
        def make_onclick(card_id):
            def _onclick(evt):
                asyncio.create_task(play_card(card_id))
            return _onclick

        handler = create_proxy(make_onclick(cid))
        event_proxies.append(handler)
        im.addEventListener("click", handler)

        # ★★★ ここが超安全：r/cidx を必ず定義してから使う ★★★
        r = 0
        cidx = idx

        if use_stack:
            r = idx // max_per_row
            cidx = idx % max_per_row
            if r >= 3:
                r = 2

            left = cidx * step_x
            top = base_top + r * step_y

            im.classList.add("stack")
            im.style.left = f"{left}px"
            im.style.top = f"{top}px"
            im.style.zIndex = str(idx)
        else:
            im.style.position = "static"

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
        cpuA = [deck.pop() for _ in range(18)] #テスト用
        cpuB = [deck.pop() for _ in range(5)]
        cpuC = [deck.pop() for _ in range(5)]

        # 場に1枚（表）
        field = deck.pop()

        # 画像初期化（リンク切れ防止）
        field_img.src = _cards.getUrl(field)
        deck_img.src = _cards.getUrl(0)

        set_msg("配布しました。\n同じマーク or 同じ数字を場に出す。\n出せるカードが無いときは山から1枚取る。", ok=True)
        render_all()

        # 山札クリック
        def on_deck_click(evt):
            asyncio.create_task(draw_from_deck())

        # 二重登録防止のため、毎回入れ替え
        deck_img.onclick = on_deck_click

    finally:
        busy = False

async def tap_card(card_id: int):
    global selected

    # 1回目：選択
    if selected != card_id:
        selected = card_id
        render_hand()  # 選択表示だけ更新（全体render_allでもOK）
        return

    # 2回目：同じカード→出す試行
    await play_card(card_id)

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
        
        # ★手札が1枚のときは「ドボン宣言」以外では上がれないので出せない
        if len(you) == 1:
            target = card_to_suit_rank(field)[1]
            total = card_to_suit_rank(you[0])[1]
            if total == target:
                set_msg("手札が1枚です。カードは出さずに「ドボン！」を押してください。", ok=True)
            else:
                set_msg("手札が1枚→ドボンのみ上がり。\nドボンできないので山から1枚取る。", ng=True)
            return

        if not can_play(card_id, field):
            set_msg("そのカードは場に出せません。\n（同じマーク か 同じ数字）", ng=True)
            return

        # 場に出す
        you.remove(card_id)
        field = card_id
        selected = None
        set_msg("場に出しました。", ok=True)
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
            set_msg("出せるカードがあります。→手札から場に出す。", ng=True)
            return

        c = deck.pop()
        you.append(c)
        selected = None
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
