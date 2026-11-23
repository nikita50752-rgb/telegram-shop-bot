# 🛍 Shop Bot: an online store inside Telegram

A ready-to-use Telegram bot that takes orders for a small business, such as a café, bakery, flower shop or local store. Customers browse the menu, fill a cart and place an order without leaving Telegram. The owner gets every order instantly and updates its status with one tap.

## What it does

**For customers**
- 🛍 **Catalog:** browse categories and product cards with descriptions and prices.
- 🛒 **Cart:** use ➖ and ➕ buttons and see a running total. A minimum order sum is supported.
- ✅ **Checkout:** name → phone (one tap with "Share my number") → pickup or delivery (with address) → comment → confirm.
- 🚗 **Delivery price:** delivery can be **free above a set sum**, for example free from 1,500 ₽.
- 📦 **My orders:** order history with live statuses, plus a notification on every status change.
- The bot remembers the customer's name for the next order.

**For the owner**
- 🆕 Each new order arrives instantly with the full details: items, total, contact and address.
- Status buttons: **Accept → On the way / Ready → Done**, or **Cancel**. The customer is notified automatically.
- `/orders` lists the latest 20 orders with their statuses.
- The whole shop is set in **one file, `catalog.json`**: categories, products, prices, delivery methods, hours and contacts. No coding is needed.

The interface is in Russian and English. The bot picks the language from the customer's Telegram settings, and customers can switch it with one button.

## Demo flow

```
🛍 Catalog → ☕ Coffee → Cappuccino · 250 ₽ → ➕ Add to cart
🛒 Cart: Cappuccino × 2, Cheesecake × 1 — Total: 790 ₽ → ✅ Checkout
→ name → 📱 phone → 🚗 Courier delivery · 150 ₽ → address → "no sugar" → ✅ Confirm
Customer: 🎉 Order #17 is placed!
Owner:    🆕 Order #17 … [👨‍🍳 Accept] [❌ Cancel]
Customer: 📦 Order #17: 👨‍🍳 being prepared
```

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
# put your BotFather token and the owner's Telegram ID into .env
python bot.py
```

Edit `catalog.json` to set your products. The example is a coffee shop with 3 categories and 9 products.

## Tech

Python 3.10+, [aiogram 3](https://docs.aiogram.dev) with a finite-state machine for checkout, and SQLite for carts and orders. The whole bot is one file of about 550 lines.

## Custom versions

Possible custom versions include:
- online payment through Telegram Payments, YooKassa or Stripe;
- product photos and a Telegram Mini App storefront;
- stock tracking and order export to Google Sheets or a CRM;
- promo codes and loyalty points;
- several branches with their own staff chats;
- broadcasts to customers.

---

### 🇷🇺 Кратко по-русски

Это интернет-магазин в Telegram: каталог, корзина, оформление заказа с доставкой или самовывозом. Владелец получает каждый заказ и меняет его статус кнопками, а клиент получает уведомление о каждом новом статусе. Товары, цены и доставка настраиваются в файле `catalog.json`. Интерфейс на русском и английском.
