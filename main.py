from js import document, window
import random
import asyncio

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

    # ルール：出せるカードがあるなら山は引けない（今段階の仕様）
    if has_playable():
        deck_img.classList.add("disabled")
    else:
        deck_img.classList.remove("disabled")

def render_field():
    if field is None:
        field_img.src = _cards.getUrl(0)
    else:
        field_img.src = _cards.getUrl(field)

def render_hand():
    clear_node(your_hand)

    playable = set()
    if field is not None:
        for c in you:
            if can_play(c, field):
                playable.add(c)

    for c in you:
        im = img_el(_cards.getUrl(c), "hand-card")
        im.dataset.cardId = str(c)

        # 出せないカードは薄く（ただしクリックは可能→理由表示のため）
        if field is not None and c not in playable:
            im.classList.add("disabled")

        def make_onclick(card_id):
            def _onclick(evt):
                asyncio.create_task(play_card(card_id))
            return _onclick

        im.addEventListener("click", make_onclick(c))
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

        if card_id not in you:
            return

        if not can_play(card_id, field):
            set_msg("そのカードは場に出せません（同じマーク または 同じ数字 ではありません）。\n出せるカードが無いなら山札をクリックして1枚取ります。", ng=True)
            return

        # 場に出す：手札から削除→場札更新
        you.remove(card_id)
        field = card_id

        set_msg("場に出しました。", ok=True)
        render_all()

        # ★この先：ここで「ドボン！」判定やCPUの手番に進める
        # （今回はここまで）

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

        # ルール：出せるカードがあるなら山札を引けない（今段階）
        if has_playable():
            set_msg("出せるカードがあります。まず手札から場に出してください。", ng=True)
            return

        c = deck.pop()
        you.append(c)
        set_msg("山札から1枚取りました。新しく出せるカードがあるか確認してください。", ok=True)
        render_all()

    finally:
        busy = False

# ===== PyScript entry points =====
def reset_game(event=None):
    asyncio.create_task(reset_async())

# init
asyncio.create_task(reset_async())
