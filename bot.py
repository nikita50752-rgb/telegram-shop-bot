"""
Shop Bot — a small online shop inside Telegram (cafes, bakeries, flower shops, stores).

Features:
  * catalog with categories and product cards (from catalog.json — no coding to change it)
  * cart with +/- buttons, running total, minimum order sum
  * checkout: name -> phone (one tap) -> pickup or delivery (+ address) -> comment -> confirm
  * delivery price, free delivery from a set sum
  * the owner gets every order instantly with status buttons: accept / on the way / done / cancel
  * the client is notified about every status change and can see "My orders"
  * /orders for the owner: the latest orders and their status
  * Russian / English interface (auto-detected from Telegram, switchable)

Run:  python bot.py   (settings are read from .env, see .env.example)
"""

import asyncio
import html
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)

BASE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- settings
def load_env(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE per line), so no extra dependency is needed."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env(BASE / ".env")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
TZ = timezone(timedelta(hours=int(os.environ.get("TZ_OFFSET_HOURS", "7"))))

SHOP = json.loads((BASE / "catalog.json").read_text(encoding="utf-8"))
CATS: dict = SHOP["categories"]
PRODUCTS = {pid: {**p, "cat": cid} for cid, c in CATS.items() for pid, p in c["products"].items()}
DELIVERY: dict = SHOP["delivery"]

# ---------------------------------------------------------------- texts (RU / EN)
T = {
    "start": {"ru": "👋 Добро пожаловать в <b>{name}</b>!\nЗакажите прямо здесь — мы всё приготовим.",
              "en": "👋 Welcome to <b>{name}</b>!\nOrder right here and we'll get it ready."},
    "btn_catalog": {"ru": "🛍 Каталог", "en": "🛍 Catalog"},
    "btn_cart": {"ru": "🛒 Корзина", "en": "🛒 Cart"},
    "btn_orders": {"ru": "📦 Мои заказы", "en": "📦 My orders"},
    "btn_info": {"ru": "ℹ️ Контакты", "en": "ℹ️ Contacts"},
    "btn_lang": {"ru": "🌐 English", "en": "🌐 Русский"},
    "btn_menu": {"ru": "🏠 Меню", "en": "🏠 Menu"},
    "btn_back": {"ru": "⬅️ Назад", "en": "⬅️ Back"},
    "choose_cat": {"ru": "Выберите раздел:", "en": "Choose a section:"},
    "product": {"ru": "<b>{name}</b>\n{desc}\n\n💰 {price}\nВ корзине: {qty}",
                "en": "<b>{name}</b>\n{desc}\n\n💰 {price}\nIn cart: {qty}"},
    "btn_add": {"ru": "➕ В корзину", "en": "➕ Add to cart"},
    "added": {"ru": "Добавлено ✅", "en": "Added ✅"},
    "cart_empty": {"ru": "🛒 Корзина пуста. Загляните в каталог!", "en": "🛒 Your cart is empty. Take a look at the catalog!"},
    "cart": {"ru": "🛒 <b>Корзина</b>\n\n{lines}\n\n<b>Итого: {total}</b>", "en": "🛒 <b>Cart</b>\n\n{lines}\n\n<b>Total: {total}</b>"},
    "min_order": {"ru": "\n\nМинимальная сумма заказа — {min}.", "en": "\n\nMinimum order is {min}."},
    "btn_checkout": {"ru": "✅ Оформить заказ", "en": "✅ Checkout"},
    "btn_clear": {"ru": "🗑 Очистить", "en": "🗑 Clear"},
    "ask_name": {"ru": "Как вас зовут?", "en": "What is your name?"},
    "ask_phone": {"ru": "Ваш телефон — нажмите кнопку ниже или напишите номер.",
                  "en": "Your phone number: tap the button below or type it."},
    "btn_phone": {"ru": "📱 Отправить мой номер", "en": "📱 Share my number"},
    "bad_phone": {"ru": "Похоже, это не номер телефона. Попробуйте ещё раз.", "en": "That doesn't look like a phone number. Try again."},
    "ask_delivery": {"ru": "Как получить заказ?", "en": "How would you like to get your order?"},
    "ask_address": {"ru": "Адрес доставки (улица, дом, квартира):", "en": "Delivery address (street, building, apartment):"},
    "ask_comment": {"ru": "Комментарий к заказу? (например, «без сахара»). Или нажмите «Пропустить».",
                    "en": "Any comment for the order? (e.g. “no sugar”). Or tap “Skip”."},
    "btn_skip": {"ru": "Пропустить", "en": "Skip"},
    "confirm": {"ru": "Проверьте заказ:\n\n{lines}\n{delivery_line}\n<b>Итого: {total}</b>\n\n👤 {name}, {phone}{address}{comment}\n\nВсё верно?",
                "en": "Please check your order:\n\n{lines}\n{delivery_line}\n<b>Total: {total}</b>\n\n👤 {name}, {phone}{address}{comment}\n\nIs everything correct?"},
    "delivery_line": {"ru": "{name}: {price}", "en": "{name}: {price}"},
    "free": {"ru": "бесплатно", "en": "free"},
    "btn_yes": {"ru": "✅ Подтвердить", "en": "✅ Confirm"},
    "btn_no": {"ru": "❌ Отменить", "en": "❌ Cancel"},
    "placed": {"ru": "🎉 Заказ <b>#{id}</b> принят! Мы напишем, когда начнём готовить.",
               "en": "🎉 Order <b>#{id}</b> is placed! We'll message you when we start preparing it."},
    "checkout_cancelled": {"ru": "Оформление отменено, корзина сохранена.", "en": "Checkout cancelled, your cart is saved."},
    "orders_empty": {"ru": "Заказов пока нет.", "en": "No orders yet."},
    "orders_head": {"ru": "📦 <b>Ваши заказы</b>", "en": "📦 <b>Your orders</b>"},
    "info": {"ru": "<b>{name}</b>\n📍 {address}\n📞 {phone}\n🕙 {hours}", "en": "<b>{name}</b>\n📍 {address}\n📞 {phone}\n🕙 {hours}"},
    "status_new": {"ru": "🆕 новый", "en": "🆕 new"},
    "status_accepted": {"ru": "👨‍🍳 готовится", "en": "👨‍🍳 being prepared"},
    "status_shipped": {"ru": "🚗 в пути / готов к выдаче", "en": "🚗 on the way / ready for pickup"},
    "status_done": {"ru": "✔️ выполнен", "en": "✔️ completed"},
    "status_cancelled": {"ru": "❌ отменён", "en": "❌ cancelled"},
    "status_changed": {"ru": "📦 Заказ <b>#{id}</b>: {status}", "en": "📦 Order <b>#{id}</b>: {status}"},
    # owner side
    "adm_new": {"ru": "🆕 <b>Заказ #{id}</b>\n\n{lines}\n{delivery_line}\n<b>Итого: {total}</b>\n\n👤 {name}, {phone}{username}{address}{comment}",
                "en": "🆕 <b>Order #{id}</b>\n\n{lines}\n{delivery_line}\n<b>Total: {total}</b>\n\n👤 {name}, {phone}{username}{address}{comment}"},
    "adm_status": {"ru": "Статус: {status}", "en": "Status: {status}"},
    "btn_accept": {"ru": "👨‍🍳 Принять", "en": "👨‍🍳 Accept"},
    "btn_ship": {"ru": "🚗 Отправлен/готов", "en": "🚗 Sent/ready"},
    "btn_done": {"ru": "✔️ Выполнен", "en": "✔️ Done"},
    "btn_cancel": {"ru": "❌ Отменить", "en": "❌ Cancel"},
    "adm_list_empty": {"ru": "Заказов нет.", "en": "No orders."},
}
NEXT_STATUS = {"new": ["accepted", "cancelled"], "accepted": ["shipped", "cancelled"], "shipped": ["done"]}
STATUS_BTN = {"accepted": "btn_accept", "shipped": "btn_ship", "done": "btn_done", "cancelled": "btn_cancel"}


def t(key: str, lang: str, **kw) -> str:
    return T[key][lang].format(**kw)


def L(obj, lang: str) -> str:
    """Pick the language version from catalog.json fields like {"ru": ..., "en": ...}."""
    return obj.get(lang) or obj.get("en") or next(iter(obj.values())) if isinstance(obj, dict) else str(obj)


def money(x: int, lang: str) -> str:
    return f"{x:,}".replace(",", " ") + " " + L(SHOP["currency"], lang)


# ---------------------------------------------------------------- storage
DB = sqlite3.connect(BASE / "shop.db")
DB.executescript("""
CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT);
CREATE TABLE IF NOT EXISTS cart (user_id INTEGER, product_id TEXT, qty INTEGER, PRIMARY KEY (user_id, product_id));
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, items TEXT, delivery TEXT, delivery_price INTEGER,
    total INTEGER, name TEXT, phone TEXT, address TEXT, comment TEXT, status TEXT, created TEXT);
""")


def lang_of(user) -> str:
    row = DB.execute("SELECT lang FROM users WHERE user_id=?", (user.id,)).fetchone()
    if row:
        return row[0]
    return "ru" if (user.language_code or "").startswith(("ru", "uk", "be", "kk")) else "en"


def cart_items(uid: int) -> list[tuple[str, int]]:
    return [(p, q) for p, q in DB.execute("SELECT product_id, qty FROM cart WHERE user_id=?", (uid,)) if p in PRODUCTS]


def cart_qty(uid: int, pid: str) -> int:
    row = DB.execute("SELECT qty FROM cart WHERE user_id=? AND product_id=?", (uid, pid)).fetchone()
    return row[0] if row else 0


def cart_change(uid: int, pid: str, delta: int) -> None:
    qty = max(0, min(99, cart_qty(uid, pid) + delta))
    if qty:
        DB.execute("INSERT OR REPLACE INTO cart VALUES (?,?,?)", (uid, pid, qty))
    else:
        DB.execute("DELETE FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
    DB.commit()


def items_text(items: list[tuple[str, int]], lang: str) -> tuple[str, int]:
    lines, total = [], 0
    for pid, qty in items:
        p = PRODUCTS[pid]
        total += p["price"] * qty
        lines.append(f"• {html.escape(L(p['name'], lang))} × {qty} — {money(p['price'] * qty, lang)}")
    return "\n".join(lines), total


def delivery_price(method: str, subtotal: int) -> int:
    d = DELIVERY[method]
    return 0 if d.get("free_from") and subtotal >= d["free_from"] else d.get("price", 0)


# ---------------------------------------------------------------- keyboards
def kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=a, callback_data=b) for a, b in row] for row in rows])


def menu_kb(lang: str, uid: int) -> InlineKeyboardMarkup:
    n = sum(q for _, q in cart_items(uid))
    cart = t("btn_cart", lang) + (f" ({n})" if n else "")
    return kb([[(t("btn_catalog", lang), "cats")], [(cart, "cart"), (t("btn_orders", lang), "orders")],
               [(t("btn_info", lang), "info"), (t("btn_lang", lang), "lang")]])


def start_text(lang: str) -> str:
    return t("start", lang, name=html.escape(L(SHOP["name"], lang)))


# ---------------------------------------------------------------- client: catalog and cart
class Checkout(StatesGroup):
    name = State()
    phone = State()
    delivery = State()
    address = State()
    comment = State()
    confirm = State()


router = Router()


@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    lang = lang_of(m.from_user)
    await m.answer(start_text(lang), reply_markup=menu_kb(lang, m.from_user.id))


@router.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = lang_of(c.from_user)
    await c.message.edit_text(start_text(lang), reply_markup=menu_kb(lang, c.from_user.id))


@router.callback_query(F.data == "lang")
async def cb_lang(c: CallbackQuery, state: FSMContext):
    new = "en" if lang_of(c.from_user) == "ru" else "ru"
    DB.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (c.from_user.id, new))
    DB.commit()
    await cb_menu(c, state)


@router.callback_query(F.data == "info")
async def cb_info(c: CallbackQuery):
    lang = lang_of(c.from_user)
    await c.message.edit_text(t("info", lang, name=html.escape(L(SHOP["name"], lang)), address=html.escape(L(SHOP["address"], lang)),
                                phone=SHOP["phone"], hours=L(SHOP["hours"], lang)),
                              reply_markup=kb([[(t("btn_menu", lang), "menu")]]))


@router.callback_query(F.data == "cats")
async def cb_cats(c: CallbackQuery):
    lang = lang_of(c.from_user)
    rows = [[(L(cat["name"], lang), f"cat:{cid}")] for cid, cat in CATS.items()]
    await c.message.edit_text(t("choose_cat", lang), reply_markup=kb(rows + [[(t("btn_menu", lang), "menu")]]))


@router.callback_query(F.data.startswith("cat:"))
async def cb_cat(c: CallbackQuery):
    lang, cid = lang_of(c.from_user), c.data[4:]
    if cid not in CATS:
        return
    rows = []
    for pid, p in CATS[cid]["products"].items():
        q = cart_qty(c.from_user.id, pid)
        rows.append([(f"{L(p['name'], lang)} · {money(p['price'], lang)}" + (f" · 🛒{q}" if q else ""), f"p:{pid}")])
    rows.append([(t("btn_back", lang), "cats"), (t("btn_cart", lang), "cart")])
    await c.message.edit_text(L(CATS[cid]["name"], lang), reply_markup=kb(rows))


async def show_product(c: CallbackQuery, pid: str):
    lang, p = lang_of(c.from_user), PRODUCTS[pid]
    qty = cart_qty(c.from_user.id, pid)
    rows = [[("➖", f"q:{pid}:-1"), (f"🛒 {qty}", "noop"), ("➕", f"q:{pid}:1")]] if qty else [[(t("btn_add", lang), f"q:{pid}:1")]]
    rows.append([(t("btn_back", lang), f"cat:{p['cat']}"), (t("btn_cart", lang), "cart")])
    await c.message.edit_text(t("product", lang, name=html.escape(L(p["name"], lang)), desc=html.escape(L(p.get("desc", {}), lang)),
                                price=money(p["price"], lang), qty=qty), reply_markup=kb(rows))


@router.callback_query(F.data.startswith("p:"))
async def cb_product(c: CallbackQuery):
    if c.data[2:] in PRODUCTS:
        await show_product(c, c.data[2:])


@router.callback_query(F.data.startswith("q:"))
async def cb_qty(c: CallbackQuery):
    _, pid, delta = c.data.split(":")
    if pid not in PRODUCTS:
        return
    cart_change(c.from_user.id, pid, int(delta))
    if int(delta) > 0:
        await c.answer(t("added", lang_of(c.from_user)))
    await show_product(c, pid)


@router.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery):
    await c.answer()


def cart_view(uid: int, lang: str):
    items = cart_items(uid)
    if not items:
        return t("cart_empty", lang), kb([[(t("btn_catalog", lang), "cats"), (t("btn_menu", lang), "menu")]])
    lines, total = items_text(items, lang)
    text = t("cart", lang, lines=lines, total=money(total, lang))
    rows = [[(f"➖  {L(PRODUCTS[pid]['name'], lang)} × {q}", f"cq:{pid}:-1"), ("➕", f"cq:{pid}:1")] for pid, q in items]
    if total < SHOP.get("min_order", 0):
        text += t("min_order", lang, min=money(SHOP["min_order"], lang))
    else:
        rows.append([(t("btn_checkout", lang), "checkout")])
    rows.append([(t("btn_clear", lang), "clear"), (t("btn_catalog", lang), "cats"), (t("btn_menu", lang), "menu")])
    return text, kb(rows)


@router.callback_query(F.data == "cart")
async def cb_cart(c: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = cart_view(c.from_user.id, lang_of(c.from_user))
    await c.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("cq:"))
async def cb_cart_qty(c: CallbackQuery, state: FSMContext):
    _, pid, delta = c.data.split(":")
    cart_change(c.from_user.id, pid, int(delta))
    await cb_cart(c, state)


@router.callback_query(F.data == "clear")
async def cb_clear(c: CallbackQuery, state: FSMContext):
    DB.execute("DELETE FROM cart WHERE user_id=?", (c.from_user.id,))
    DB.commit()
    await cb_cart(c, state)


# ---------------------------------------------------------------- client: checkout
@router.callback_query(F.data == "checkout")
async def cb_checkout(c: CallbackQuery, state: FSMContext):
    lang = lang_of(c.from_user)
    if not cart_items(c.from_user.id):
        await cb_cart(c, state)
        return
    await state.set_state(Checkout.name)
    last = DB.execute("SELECT name FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (c.from_user.id,)).fetchone()
    hint = kb([[(last[0], "same_name")]]) if last else None
    await c.message.edit_text(t("ask_name", lang), reply_markup=hint)


async def ask_phone(m: Message, state: FSMContext, lang: str, name: str):
    await state.update_data(name=name[:60])
    await state.set_state(Checkout.phone)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t("btn_phone", lang), request_contact=True)]],
                                 resize_keyboard=True, one_time_keyboard=True)
    await m.answer(t("ask_phone", lang), reply_markup=markup)


@router.callback_query(Checkout.name, F.data == "same_name")
async def cb_same_name(c: CallbackQuery, state: FSMContext):
    last = DB.execute("SELECT name FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (c.from_user.id,)).fetchone()
    await ask_phone(c.message, state, lang_of(c.from_user), last[0] if last else c.from_user.full_name)


@router.message(Checkout.name, F.text)
async def got_name(m: Message, state: FSMContext):
    await ask_phone(m, state, lang_of(m.from_user), m.text.strip())


@router.message(Checkout.phone, F.contact | F.text)
async def got_phone(m: Message, state: FSMContext):
    lang = lang_of(m.from_user)
    phone = m.contact.phone_number if m.contact else m.text.strip()
    if len(re.sub(r"\D", "", phone)) < 7:
        await m.answer(t("bad_phone", lang))
        return
    await state.update_data(phone=phone[:30])
    await state.set_state(Checkout.delivery)
    await m.answer("👍", reply_markup=ReplyKeyboardRemove())
    subtotal = items_text(cart_items(m.from_user.id), lang)[1]
    rows = []
    for key, d in DELIVERY.items():
        price = delivery_price(key, subtotal)
        rows.append([(f"{L(d['name'], lang)} · {money(price, lang) if price else t('free', lang)}", f"dl:{key}")])
    await m.answer(t("ask_delivery", lang), reply_markup=kb(rows))


@router.callback_query(Checkout.delivery, F.data.startswith("dl:"))
async def got_delivery(c: CallbackQuery, state: FSMContext):
    lang, key = lang_of(c.from_user), c.data[3:]
    if key not in DELIVERY:
        return
    await state.update_data(delivery=key)
    if DELIVERY[key].get("needs_address"):
        await state.set_state(Checkout.address)
        await c.message.edit_text(t("ask_address", lang))
    else:
        await state.update_data(address="")
        await ask_comment(c.message, state, lang, edit=True)


async def ask_comment(m: Message, state: FSMContext, lang: str, edit: bool = False):
    await state.set_state(Checkout.comment)
    markup = kb([[(t("btn_skip", lang), "skip_comment")]])
    if edit:
        await m.edit_text(t("ask_comment", lang), reply_markup=markup)
    else:
        await m.answer(t("ask_comment", lang), reply_markup=markup)


@router.message(Checkout.address, F.text)
async def got_address(m: Message, state: FSMContext):
    await state.update_data(address=m.text.strip()[:200])
    await ask_comment(m, state, lang_of(m.from_user))


def order_summary(uid: int, data: dict, lang: str) -> dict:
    items = cart_items(uid)
    lines, subtotal = items_text(items, lang)
    dprice = delivery_price(data["delivery"], subtotal)
    return {
        "items": items, "lines": lines, "delivery_price": dprice, "total": subtotal + dprice,
        "delivery_line": t("delivery_line", lang, name=L(DELIVERY[data["delivery"]]["name"], lang),
                           price=money(dprice, lang) if dprice else t("free", lang)),
    }


async def show_confirm(m: Message, state: FSMContext, uid: int, lang: str, edit: bool):
    data = await state.get_data()
    s = order_summary(uid, data, lang)
    await state.set_state(Checkout.confirm)
    text = t("confirm", lang, lines=s["lines"], delivery_line=s["delivery_line"], total=money(s["total"], lang),
             name=html.escape(data["name"]), phone=html.escape(data["phone"]),
             address=f"\n📍 {html.escape(data['address'])}" if data.get("address") else "",
             comment=f"\n💬 {html.escape(data['comment'])}" if data.get("comment") else "")
    markup = kb([[(t("btn_yes", lang), "place"), (t("btn_no", lang), "cart")]])
    if edit:
        await m.edit_text(text, reply_markup=markup)
    else:
        await m.answer(text, reply_markup=markup)


@router.callback_query(Checkout.comment, F.data == "skip_comment")
async def skip_comment(c: CallbackQuery, state: FSMContext):
    await state.update_data(comment="")
    await show_confirm(c.message, state, c.from_user.id, lang_of(c.from_user), edit=True)


@router.message(Checkout.comment, F.text)
async def got_comment(m: Message, state: FSMContext):
    await state.update_data(comment=m.text.strip()[:300])
    await show_confirm(m, state, m.from_user.id, lang_of(m.from_user), edit=False)


def admin_kb(order_id: int, status: str, lang: str) -> InlineKeyboardMarkup | None:
    nxt = NEXT_STATUS.get(status, [])
    return kb([[(t(STATUS_BTN[s], lang), f"st:{order_id}:{s}") for s in nxt]]) if nxt else None


def admin_text(order_id: int, lang: str) -> str:
    o = DB.execute("SELECT user_id, items, delivery, delivery_price, total, name, phone, address, comment, status FROM orders WHERE id=?",
                   (order_id,)).fetchone()
    uid, items, delivery, dprice, total, name, phone, address, comment, status = o
    lines, _ = items_text([tuple(x) for x in json.loads(items)], lang)
    text = t("adm_new", lang, id=order_id, lines=lines,
             delivery_line=t("delivery_line", lang, name=L(DELIVERY[delivery]["name"], lang),
                             price=money(dprice, lang) if dprice else t("free", lang)),
             total=money(total, lang), name=html.escape(name), phone=html.escape(phone),
             username=f' · <a href="tg://user?id={uid}">Telegram</a>',
             address=f"\n📍 {html.escape(address)}" if address else "",
             comment=f"\n💬 {html.escape(comment)}" if comment else "")
    return text + "\n\n" + t("adm_status", lang, status=t("status_" + status, lang))


@router.callback_query(Checkout.confirm, F.data == "place")
async def cb_place(c: CallbackQuery, state: FSMContext, bot: Bot):
    lang, uid = lang_of(c.from_user), c.from_user.id
    data = await state.get_data()
    s = order_summary(uid, data, lang)
    if not s["items"]:
        await cb_cart(c, state)
        return
    cur = DB.execute("INSERT INTO orders (user_id, items, delivery, delivery_price, total, name, phone, address, comment, status, created) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (uid, json.dumps(s["items"]), data["delivery"], s["delivery_price"], s["total"], data["name"],
                      data["phone"], data.get("address", ""), data.get("comment", ""), "new", datetime.now(TZ).isoformat()))
    DB.execute("DELETE FROM cart WHERE user_id=?", (uid,))
    DB.commit()
    await state.clear()
    oid = cur.lastrowid
    await c.message.edit_text(t("placed", lang, id=oid), reply_markup=menu_kb(lang, uid))
    for admin in ADMIN_IDS:
        try:
            alang = DB.execute("SELECT lang FROM users WHERE user_id=?", (admin,)).fetchone()
            alang = alang[0] if alang else "ru"
            await bot.send_message(admin, admin_text(oid, alang), reply_markup=admin_kb(oid, "new", alang))
        except Exception as e:
            logging.warning("cannot notify admin %s: %s", admin, e)


@router.callback_query(F.data == "orders")
async def cb_orders(c: CallbackQuery):
    lang = lang_of(c.from_user)
    rows = DB.execute("SELECT id, total, status, created FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
                      (c.from_user.id,)).fetchall()
    if not rows:
        text = t("orders_empty", lang)
    else:
        text = t("orders_head", lang) + "\n\n" + "\n".join(
            f"#{oid} · {datetime.fromisoformat(cr).strftime('%d.%m %H:%M')} · {money(total, lang)} · {t('status_' + st, lang)}"
            for oid, total, st, cr in rows)
    await c.message.edit_text(text, reply_markup=kb([[(t("btn_menu", lang), "menu")]]))


# ---------------------------------------------------------------- owner
@router.callback_query(F.data.startswith("st:"))
async def cb_status(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        await c.answer()
        return
    _, oid, new = c.data.split(":")
    oid = int(oid)
    row = DB.execute("SELECT user_id, status FROM orders WHERE id=?", (oid,)).fetchone()
    if not row or new not in NEXT_STATUS.get(row[1], []):
        await c.answer("—")
        return
    DB.execute("UPDATE orders SET status=? WHERE id=?", (new, oid))
    DB.commit()
    lang = lang_of(c.from_user)
    await c.message.edit_text(admin_text(oid, lang), reply_markup=admin_kb(oid, new, lang))
    client = row[0]
    clang = DB.execute("SELECT lang FROM users WHERE user_id=?", (client,)).fetchone()
    clang = clang[0] if clang else "ru"
    try:
        await bot.send_message(client, t("status_changed", clang, id=oid, status=t("status_" + new, clang)))
    except Exception as e:
        logging.warning("cannot notify client %s: %s", client, e)


@router.message(Command("orders"))
async def cmd_orders(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    lang = lang_of(m.from_user)
    rows = DB.execute("SELECT id, name, total, status, created FROM orders ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        await m.answer(t("adm_list_empty", lang))
        return
    await m.answer("\n".join(
        f"#{oid} · {datetime.fromisoformat(cr).strftime('%d.%m %H:%M')} · {html.escape(name)} · {money(total, lang)} · {t('status_' + st, lang)}"
        for oid, name, total, st, cr in rows))


@router.message(F.text)
async def fallback(m: Message, state: FSMContext):
    await cmd_start(m, state)


async def main():
    if not BOT_TOKEN or BOT_TOKEN.startswith("123456789:"):
        raise SystemExit("Put your bot token from @BotFather into .env (see .env.example)")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from aiogram.client.default import DefaultBotProperties
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
