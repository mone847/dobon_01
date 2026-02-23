from js import document, window
import random
import asyncio
from pyodide.ffi import create_proxy
from typing import Callable, Optional

event_proxies = []

# ===== DOM =====
cpuA_title = document.getElementById("cpuA-title")
cpuB_title = document.getElementById("cpuB-title")
cpuC_title = document.getElementById("cpuC-title")
you_title = document.getElementById("you-title")
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
discard=[]       # 捨て札

TURN_ORDER = ["you", "cpuA", "cpuB", "cpuC"]
current_player_idx = 0
current_player = "you"
dobon_waiting = False
win_stats = {
    "you":  {"win": 0, "total": 0},
    "cpuA": {"win": 0, "total": 0},
    "cpuB": {"win": 0, "total": 0},
    "cpuC": {"win": 0, "total": 0},
}

game_over = False  # 勝敗がついたら True

selected = None  # iPad向け：選択中カードid（1回目タップで選択）

busy = False

last_actor = None  # 最後に行動したプレーヤー

def win_rate_str(player: str) -> str:
    w = win_stats[player]["win"]
    t = win_stats[player]["total"]
    rate = (w / t * 100) if t > 0 else 0
    return f"{w}勝/{t}回中（勝率{rate:.1f}%）"

def render_cpu(panel_title_el, panel_cards_el, name: str, cards_list, pid: str):
    n = len(cards_list)
    stats = win_rate_str(pid)
    panel_title_el.innerText = f"{name}（{n}枚）\n{stats}"

# ---- カード番号→(スート,数字)の割り当て ----
# c1..c52 の並びは「♣→♦→♥→♠（各A..K）」
def card_to_suit_rank(i: int):
    suit_index = (i - 1) // 13  # 0..3
    rank = (i - 1) % 13 + 1     # 1..13
    suits = ["C", "D", "H", "S"]  # ♣ ♦ ♥ ♠ 
    return suits[suit_index], rank

def dobon_possible():
    """
    ルール：手札「すべて」の合計が、場の数字と一致したらドボン可能
    戻り値：(ok, used)
      ok: bool
      used: list（将来拡張用。今は手札全部を返す）
    """
    if field is None or len(you) == 0:
        return False, []

    target = card_to_suit_rank(field)[1]
    total = sum(card_to_suit_rank(cid)[1] for cid in you)

    ok = (total == target)
    used = you[:] if ok else []
    return ok, used


def can_play(card_id: int, field_id: int) -> bool:
    s1, r1 = card_to_suit_rank(card_id)
    s2, r2 = card_to_suit_rank(field_id)
    return (s1 == s2) or (r1 == r2)

def has_playable():
    if field is None:
        return False
    # ★残り1枚は「ドボン宣言」以外では出せない＝playable扱いにしない
    if len(you) == 1:
        return False

    return any(can_play(cid, field) for cid in you)


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
    # ===== タイトル =====
    n = len(cards_list)
    panel_title_el.innerText = f"{name}（{n}枚）"

    clear_node(panel_cards_el)

    if n <= 0:
        panel_cards_el.style.minHeight = "70px"
        return

    back = _cards.getUrl(0)

    # ===== コンテナ幅 =====
    w = int(panel_cards_el.clientWidth) if panel_cards_el.clientWidth else 260
    avail = max(120, w - 8)

    card_w = 52
    gap = 10

    total_normal = n * card_w + max(0, n - 1) * gap

    THRESHOLD = 8  # 8枚までは通常表示

    # ===== 通常表示かstackか判定 =====
    if n <= THRESHOLD and total_normal <= avail:
        use_stack = False
    else:
        use_stack = True

    panel_cards_el.style.position = "relative"
    if use_stack:
        panel_cards_el.style.minHeight = "78px"
    else:
        panel_cards_el.style.minHeight = "70px"

    # ===== 描画 =====
    for idx in range(n):
        im = img_el(back, "cpu-card")

        if use_stack:
            # 自動 step_x 計算
            if n == 1:
                step_x = 0
            else:
                # 「最後のカードが右端に来る」ように計算
                step_x = (avail - card_w) / (n - 1)
                step_x = max(6, min(18, step_x))  # 最小6px、最大18pxに制限

            left = idx * step_x
            top = 2

            im.classList.add("stack")
            im.style.left = f"{left}px"
            im.style.top = f"{top}px"
            im.style.zIndex = str(idx)
        else:
            im.classList.remove("stack")
            im.style.position = "static"

        panel_cards_el.appendChild(im)

def render_you_title():
    n = len(you)
    stats = win_rate_str("you")
    you_title.innerText = f"あなた（{n}枚）\n{stats}"

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
    render_cpu(cpuA_title, cpuA_cards, "プレーヤーA", cpuA, "cpuA")
    render_cpu(cpuB_title, cpuB_cards, "プレーヤーB", cpuB, "cpuB")
    render_cpu(cpuC_title, cpuC_cards, "プレーヤーC", cpuC, "cpuC")
    render_you_title()
    render_field()
    render_deck()
    render_hand()
    dobon_btn = document.getElementById("dobon-btn")
    if can_dobon():   # 判定関数
        dobon_btn.classList.add("ready")
    else:
        dobon_btn.classList.remove("ready") 

# ===== Actions =====
async def reset_async():
    global deck, field, discard
    global you, cpuA, cpuB, cpuC
    global busy, game_over, dobon_waiting
    global current_player_idx, current_player
    global selected, last_actor
    
    if busy:
        return
    busy = True
    try:
        await ensure_cards()

        # ===== 全フラグ完全リセット =====
        game_over = False
        dobon_waiting = False
        selected = None
        last_actor = None

        current_player_idx = 0
        current_player = TURN_ORDER[current_player_idx]

        # シャッフル
        deck = list(range(1, 53))
        random.shuffle(deck)
        # ★ここで discard をクリア
        discard = []

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
        # UI初期化
        deck_img.classList.remove("disabled")
        dobon_btn.disabled = False
        set_dobon_alert(False)        
        set_turn_ui("you")
        set_msg("Newゲーム！。同じマーク or 同じ数字\n出せるカードが無い→山から取る。", ok=True)
        
        render_all()
        
        current_player_idx = 0
        current_player = TURN_ORDER[current_player_idx]  # = "you"
        
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
    global field, busy, selected, last_actor
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

        # いまの場札を捨て札へ
        if field is not None:
            discard.append(field)
        # 新しい場札へ
        field = card_id
        selected = None

        # ★追加：この手番で“行動した人”を記録
        last_actor = "you"   # 将来CPU実装したら current_player で入れる

        set_msg("場に出しました。\n", ok=True)
        render_all()
        # you が行動したので次へ
        next_player()
        asyncio.create_task(run_cpu_turns_until_you())

    finally:
        busy = False


async def draw_from_deck():
    global busy, selected, last_actor

    if busy:
        return

    busy = True
    try:
        # ===== 山札補充チェック =====
        refilled = refill_deck_if_empty()

        if len(deck) == 0:
            set_msg("山札も捨て札もありません。\n", ng=True)
            return

        # ===== 出せるカードがあるなら引けない =====
        if has_playable():
            set_msg("出せるカードあり。→手札から出す。\n", ng=True)
            return

        # ===== 山札から引く =====
        c = deck.pop()
        you.append(c)
        selected = None

        # ★追加：引いたのも“行動”なので記録（次にドボンされたらこの人が負け）
        last_actor = "you"  # 将来CPU実装したら current_player で入れる

        # ===== メッセージ制御 =====
        if refilled:
            set_msg("山札を再構築しました。\n山札から1枚取りました。\n", ok=True)
        else:
            set_msg("山札から1枚取りました。\n", ok=True)

        render_all()
        next_player()
        asyncio.create_task(run_cpu_turns_until_you())

    finally:
        busy = False

def card_label(cid: int) -> str:
    s, r = card_to_suit_rank(cid)
    suit_symbol = {"C":"♣","D":"♦","H":"♥","S":"♠"}.get(s, s)
    return f"{suit_symbol}{r}"

def hand_sum(cards):
    return sum(card_to_suit_rank(cid)[1] for cid in cards)

async def try_dobon_async():
    global busy, game_over, dobon_waiting, last_actor

    if busy:
        return

    busy = True
    try:
        ok, used = dobon_possible()

        target = card_to_suit_rank(field)[1]
        total = sum(card_to_suit_rank(cid)[1] for cid in you)

        # ===== ワンクッション =====
        if ok and last_actor == "you":
            set_msg(
                "ドボン・準備完了！\n"
                "次の人の手番後に「ドボン！」できます。",
                ng=True
            )

            # ★CPU停止中なら再開
            if dobon_waiting:
                dobon_waiting = False
                set_dobon_alert(False)
                asyncio.create_task(run_cpu_turns_until_you())
            return

        # ===== ドボン失敗 =====
        if not ok:
            set_msg(
                f"ドボンできません。\n"
                f"手札の合計：{total}  場の数字：{target}",
                ng=True
            )

            if dobon_waiting:
                dobon_waiting = False
                set_dobon_alert(False)
                asyncio.create_task(run_cpu_turns_until_you())
            return

        # ===== 勝利 =====
        loser = last_actor if last_actor is not None else "（不明）"

        set_msg(
            "ドボン！ あなたの勝ち！\n"
            f"手札：{total} = 場：{target}  負け：{loser}",
            ok=True
        )
        win_stats["you"]["win"] += 1
        for p in win_stats:
            win_stats[p]["total"] += 1

        dobon_waiting = False
        set_dobon_alert(False)
        game_over = True

        deck_img.classList.add("disabled")
        dobon_btn.disabled = True

    finally:
        busy = False


def try_dobon(event=None):
    asyncio.create_task(try_dobon_async())

def can_dobon():
    # 手札が空なら不可
    if not you:
        return False

    # 場のカードがなければ不可
    if field is None:
        return False

    # 場の数字を取得（1～13）
    field_rank = ((field - 1) % 13) + 1

    # 手札の合計を計算
    total = 0
    for c in you:
        rank = ((c - 1) % 13) + 1
        total += rank

    return total == field_rank

def refill_deck_if_empty():
    """山札が空なら、場の一番上(field)だけ残して discard をシャッフルして山に戻す"""
    global deck, discard, field

    if len(deck) > 0:
        return False

    # discard が無ければ補充できない
    if len(discard) == 0:
        return False

    random.shuffle(discard)
    deck = discard[:]   # 山札に戻す
    discard = []        # 捨て札は空に
    return True

def set_turn_ui(player: str):
    # いったん全部OFF
    for pid in ["you-box", "cpuA-box", "cpuB-box", "cpuC-box"]:
        el = document.getElementById(pid)
        if el:
            el.classList.remove("turn-active")

    # ON
    box_id = {"you":"you-box","cpuA":"cpuA-box","cpuB":"cpuB-box","cpuC":"cpuC-box"}[player]
    el = document.getElementById(box_id)
    if el:
        el.classList.add("turn-active")

    # msg も追加
    # （すでに別メッセージを出した直後に上書きしたくないなら、render_all()の末尾で呼ぶのが安定）
    set_msg(f"{name_ja(player)} の番です。\n", ok=True)

def name_ja(player: str) -> str:
    return {
        "you":"あなた",
        "cpuA":"プレーヤーA",
        "cpuB":"プレーヤーB",
        "cpuC":"プレーヤーC",
    }[player]

def next_player():
    global current_player_idx, current_player
    current_player_idx = (current_player_idx + 1) % len(TURN_ORDER)
    current_player = TURN_ORDER[current_player_idx]
    set_turn_ui(current_player)

def get_hand(player: str) -> list[int]:
    if player == "cpuA": return cpuA
    if player == "cpuB": return cpuB
    if player == "cpuC": return cpuC
    raise ValueError("player must be cpuA/cpuB/cpuC")

async def cpu_play(player: str, card_id: int):
    global field, selected, last_actor

    hand = get_hand(player)
    if card_id not in hand:
        return

    # 残り1枚は “ドボン宣言以外で上がれない” ルール（CPUにも同様に適用）
    if len(hand) == 1:
        # 出さない
        return

    if not can_play(card_id, field):
        return

    # 捨て札へ
    if field is not None:
        discard.append(field)

    hand.remove(card_id)
    field = card_id

    # ★直前に行動した人（重要！）
    last_actor = player

    set_msg(f"{name_ja(player)} が場に出しました。\n", ok=True)
    render_all()

async def cpu_draw(player: str):
    global last_actor

    # 山札補充
    refill_deck_if_empty()
    if len(deck) == 0:
        set_msg("山札も捨て札もありません。\n", ng=True)
        return

    hand = get_hand(player)

    # 「出せるカードがあるなら必ず出す」ルール
    # ★ただし残り1枚は“ドボン以外で上がれない”ので、出せる判定にしない（＝引いてよい）
    if len(hand) > 1 and any(can_play(cid, field) for cid in hand):
        # 本来は引けない
        return

    c = deck.pop()
    hand.append(c)

    # ★直前に行動した人（重要！）
    last_actor = player

    set_msg(f"{name_ja(player)} が山から1枚取りました。\n", ok=True)
    render_all()

async def run_cpu_turns_until_you():
    global busy, game_over, current_player, last_actor, dobon_waiting

    while (not game_over) and current_player != "you":

        set_turn_ui(current_player)
        await asyncio.sleep(0.35)

        # ===== プレイヤー優先ドボンチェック =====
        if can_dobon() and last_actor != "you":
            dobon_waiting = True
            set_dobon_alert(True)
            set_msg("ドボンチャンス！「ドボン！」を押してください。\n", ok=True)
            return

        hand = get_hand(current_player)

        if field is None:
            next_player()
            continue

        # ★追加：残り1枚は必ず引く（ワンクッション/上がり禁止ルール対応）
        if len(hand) == 1:
            await cpu_draw(current_player)
        else:
            chosen = choose_card_lv1(hand, field, can_play)
            if chosen is not None:
                await cpu_play(current_player, chosen)
            else:
                await cpu_draw(current_player)

        # ===== プレイヤー優先ドボンチェック（行動後） =====
        if can_dobon() and last_actor != "you":
            dobon_waiting = True
            set_dobon_alert(True)
            set_msg("ドボンチャンス！「ドボン！」を押してください。\n", ok=True)
            return

        # ===== CPUドボン判定 =====
        hand = get_hand(current_player)
        if cpu_can_dobon(hand) and last_actor != current_player:
            loser = last_actor if last_actor else "（不明）"

            set_msg(
                f"{name_ja(current_player)} がドボン！\n"
                f"負け：{name_ja(loser)}",
                ok=True
            )
            winner = current_player
            win_stats[winner]["win"] += 1
            for p in win_stats:
                win_stats[p]["total"] += 1
            
            game_over = True
            return

        next_player()

    if not game_over:
        set_turn_ui("you")


def set_dobon_alert(on: bool):
    if on:
        dobon_btn.classList.add("dobon-alert")
    else:
        dobon_btn.classList.remove("dobon-alert")

def cpu_can_dobon(hand):
    if field is None or len(hand) == 0:
        return False
    target = card_to_suit_rank(field)[1]
    total = sum(card_to_suit_rank(c)[1] for c in hand)
    return total == target


# ===== PyScript entry points =====
def reset_game(event=None):
    global last_actor
    last_actor = None
    asyncio.create_task(reset_async())
    
# init
asyncio.create_task(reset_async())
