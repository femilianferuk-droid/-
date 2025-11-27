import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота
BOT_TOKEN = "8397723969:AAGV-qBJ8GWLYaeY_QCdRlJGZbGJhsGNLJU"

# Загрузка данных
try:
    with open('user_data.json', 'r') as f:
        user_data = json.load(f)
except:
    user_data = {}

try:
    with open('bot_settings.json', 'r') as f:
        bot_settings = json.load(f)
except:
    bot_settings = {
        "required_channels": ["@v3estnikov"],
        "admin_ids": [7973988177],
        "owner_id": 7973988177,  # ID владельца
        "referral_bonus_inviter": 5,
        "referral_bonus_invited": 2,
        "min_withdraw_amount": 10,
        "min_referrals_for_withdraw": 1
    }

# Состояния для разговора
(
    WAITING_USERNAME,
    WAITING_GIFTS_COUNT,
    WAITING_NFT_GIFTS_COUNT,
    WAITING_REVIEW,
    WAITING_WITHDRAW_AMOUNT,
    WAITING_WITHDRAW_DETAILS,
    WAITING_BROADCAST,
    WAITING_CHANNEL_ADD,
    WAITING_ADMIN_ADD
) = range(9)

def save_data():
    with open('user_data.json', 'w') as f:
        json.dump(user_data, f, indent=2)
    with open('bot_settings.json', 'w') as f:
        json.dump(bot_settings, f, indent=2)

# Стили для оформления
class Styles:
    BLUE_TITLE = "🔷 *{text}* 🔷"
    BLUE_SUBTITLE = "🔹 **{text}**"
    SUCCESS = "✅ {text}"
    ERROR = "❌ {text}"
    WARNING = "⚠️ {text}"
    MONEY = "💰 {text}"
    ADMIN = "👑 {text}"
    OWNER = "👑 *{text}*"

# Проверка прав владельца
def is_owner(user_id):
    return user_id == bot_settings["owner_id"]

# Проверка прав администратора
def is_admin(user_id):
    return user_id in bot_settings["admin_ids"]

# Клавиатуры
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Оставить отзыв", callback_data="leave_review")],
        [InlineKeyboardButton("💰 Вывод средств", callback_data="withdraw")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton("🛟 Поддержка", callback_data="support")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])

def get_withdraw_methods_keyboard():
    keyboard = [
        [InlineKeyboardButton("💳 СБП", callback_data="withdraw_sbp")],
        [InlineKeyboardButton("💳 Банковская карта", callback_data="withdraw_card")],
        [InlineKeyboardButton("₿ Crypto Bot", callback_data="withdraw_crypto")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
    ]
    
    # Только владелец может управлять каналами и админами
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("📢 Управление каналами", callback_data="admin_channels")])
        keyboard.append([InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage")])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_channels_keyboard(user_id):
    keyboard = []
    for channel in bot_settings["required_channels"]:
        keyboard.append([InlineKeyboardButton(f"❌ {channel}", callback_data=f"remove_channel_{channel}")])
    
    # Только владелец может добавлять каналы
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_manage_keyboard(user_id):
    keyboard = []
    for admin_id in bot_settings["admin_ids"]:
        # Владелец не может удалить себя
        if admin_id == bot_settings["owner_id"]:
            keyboard.append([InlineKeyboardButton(f"👑 Владелец {admin_id}", callback_data="owner_cannot_remove")])
        else:
            keyboard.append([InlineKeyboardButton(f"❌ Админ {admin_id}", callback_data=f"remove_admin_{admin_id}")])
    
    # Только владелец может добавлять админов
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# Проверка подписки на каналы (для не-админов)
async def check_subscription(user_id, context):
    # Админы пропускают проверку подписки
    if is_admin(user_id):
        return True, None
        
    for channel in bot_settings["required_channels"]:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status in ['left', 'kicked']:
                return False, channel
        except Exception as e:
            logging.error(f"Ошибка проверки подписки на {channel}: {e}")
            return False, channel
    return True, None

# Проверка условий для вывода
def check_withdraw_conditions(user_id):
    user_info = user_data.get(str(user_id), {})
    balance = user_info.get('balance', 0)
    referrals_count = len(user_info.get('referrals', []))
    
    min_amount = bot_settings.get('min_withdraw_amount', 10)
    min_refs = bot_settings.get('min_referrals_for_withdraw', 1)
    
    conditions_met = []
    
    if balance >= min_amount:
        conditions_met.append(f"✅ Баланс: {balance}₽/{min_amount}₽")
    else:
        conditions_met.append(f"❌ Баланс: {balance}₽/{min_amount}₽")
    
    if referrals_count >= min_refs:
        conditions_met.append(f"✅ Рефералов: {referrals_count}/{min_refs}")
    else:
        conditions_met.append(f"❌ Рефералов: {referrals_count}/{min_refs}")
    
    return all([
        balance >= min_amount,
        referrals_count >= min_refs
    ]), conditions_met

# Команда /start с проверкой подписки
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Инициализация пользователя
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            'balance': 0,
            'reviews_count': 0,
            'referrals': [],
            'referral_code': str(user_id),
            'invited_by': None,
            'total_earned': 0,
            'registered_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat()
        }
        save_data()
    else:
        # Обновляем время последней активности
        user_data[str(user_id)]['last_activity'] = datetime.now().isoformat()
        save_data()
    
    # Проверка реферальной ссылки
    if context.args:
        referrer_id = context.args[0]
        if referrer_id != str(user_id) and referrer_id in user_data:
            user_data[str(user_id)]['invited_by'] = referrer_id
            save_data()
    
    # Проверка подписки (только для не-админов)
    is_subscribed, channel = await check_subscription(user_id, context)
    
    if not is_subscribed:
        subscription_text = f"""
{Styles.ERROR.format(text="ПОДПИШИТЕСЬ НА КАНАЛЫ!")}

📢 Для использования бота необходимо подписаться на наши каналы:

"""
        for req_channel in bot_settings["required_channels"]:
            subscription_text += f"• {req_channel}\n"
        
        subscription_text += f"\nПосле подписки нажмите: /start"
        
        keyboard = []
        for req_channel in bot_settings["required_channels"]:
            keyboard.append([InlineKeyboardButton(f"📢 Подписаться на {req_channel}", url=f"https://t.me/{req_channel[1:]}")])
        keyboard.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")])
        
        await update.message.reply_text(
            subscription_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Главное меню
    user_info = user_data[str(user_id)]
    can_withdraw, conditions = check_withdraw_conditions(user_id)
    
    welcome_text = f"""
🎉 *Добро пожаловать в бот оплаты за отзывы!* 🎉

💎 *Ваш баланс:* {user_info['balance']}₽
👥 *Рефералов:* {len(user_info['referrals'])}
📝 *Отзывов:* {user_info['reviews_count']}

📋 *Условия вывода:*
{chr(10).join(conditions)}

{'✅ *Вывод доступен!*' if can_withdraw else '❌ *Вывод пока недоступен*'}
    """
    
    keyboard = get_main_keyboard()
    
    # Добавляем админ-панель для администратора
    if is_admin(user_id):
        keyboard.inline_keyboard.append([InlineKeyboardButton("👑 Админ Панель", callback_data="admin_panel")])
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "check_subscription":
        is_subscribed, channel = await check_subscription(user_id, context)
        if is_subscribed:
            await start(update, context)
        else:
            await query.edit_message_text(
                f"❌ Вы не подписались на канал: {channel}\n\nПожалуйста, подпишитесь и нажмите /start",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{channel[1:]}")]])
            )
        return
    
    if query.data == "leave_review":
        user_data[str(user_id)] = {
            'state': WAITING_USERNAME,
            'total_amount': 10,
            'username': '',
            'gifts_bonus': 0,
            'nft_bonus': 0,
            **user_data.get(str(user_id), {})
        }
        save_data()
        
        review_info = Styles.BLUE_TITLE.format(text="СОЗДАНИЕ ОТЗЫВА") + """

📊 *Тарифы:*
• 🎁 Обычные подарки: +3₽ за каждый
• 🖼️ NFT подарки: +8₽ за каждый
• 💰 Базовая ставка: 10₽

📋 *Требования к отзыву:*
• ✅ Обязательно укажите: @v3estnikov
• ❌ Запрещено слово: скам

👇 *Напишите ваш юзернейм в Telegram:*
        """
        
        await query.edit_message_text(
            review_info,
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "withdraw":
        can_withdraw, conditions = check_withdraw_conditions(user_id)
        
        if not can_withdraw:
            withdraw_text = Styles.BLUE_TITLE.format(text="ВЫВОД СРЕДСТВ") + f"""

❌ *Вывод временно недоступен*

📋 *Требования для вывода:*
{chr(10).join(conditions)}

💡 *Как выполнить условия:*
• 📝 Оставляйте отзывы чтобы увеличить баланс
• 👥 Приглашайте друзей по реферальной ссылке
            """
            
            await query.edit_message_text(
                withdraw_text,
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        balance = user_data.get(str(user_id), {}).get('balance', 0)
        
        withdraw_text = Styles.BLUE_TITLE.format(text="ВЫВОД СРЕДСТВ") + f"""

✅ *Все условия выполнены!*

💰 *Ваш баланс:* {balance}₽
👥 *Ваши рефералы:* {len(user_data[str(user_id)].get('referrals', []))}

👇 *Выберите способ вывода:*
        """
        
        await query.edit_message_text(
            withdraw_text,
            reply_markup=get_withdraw_methods_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "referral":
        user_info = user_data.get(str(user_id), {})
        ref_code = user_info.get('referral_code', str(user_id))
        ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start={ref_code}"
        ref_count = len(user_info.get('referrals', []))
        
        min_refs = bot_settings.get('min_referrals_for_withdraw', 1)
        
        referral_text = Styles.BLUE_TITLE.format(text="РЕФЕРАЛЬНАЯ СИСТЕМА") + f"""

👥 *Ваши рефералы:* {ref_count}/{min_refs}
💰 *Заработано с рефералов:* {ref_count * bot_settings['referral_bonus_inviter']}₽

🎁 *Бонусы:*
• Вам за каждого реферала: {bot_settings['referral_bonus_inviter']}₽
• Рефералу при первом отзыве: {bot_settings['referral_bonus_invited']}₽

⚠️ *Для вывода нужно:* {min_refs} реферал(ов)

📎 *Ваша реферальная ссылка:*
`{ref_link}`

👇 *Поделитесь ссылкой с друзьями!*
        """
        
        keyboard = [
            [InlineKeyboardButton("📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Получай+деньги+за+отзывы!")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            referral_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == "support":
        support_text = Styles.BLUE_TITLE.format(text="ПОДДЕРЖКА") + """

🛟 *Мы всегда готовы помочь!*

📞 *Контакт для связи:*
@support_username

⏰ *Время ответа:* до 24 часов
        """
        
        await query.edit_message_text(
            support_text,
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "admin_panel":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Доступ запрещен!")
            return
        
        role_text = "👑 *Владелец*" if is_owner(user_id) else "⚡ *Администратор*"
        
        admin_text = Styles.ADMIN.format(text="АДМИН ПАНЕЛЬ") + f"""

{role_text}

👥 *Админов:* {len(bot_settings['admin_ids'])}
📢 *Каналов:* {len(bot_settings['required_channels'])}

👇 *Выберите действие:*
        """
        
        await query.edit_message_text(
            admin_text,
            reply_markup=get_admin_keyboard(user_id),
            parse_mode='Markdown'
        )
    
    elif query.data == "admin_stats":
        if not is_admin(user_id):
            return
        
        total_users = len(user_data)
        total_reviews = sum(user.get('reviews_count', 0) for user in user_data.values())
        total_balance = sum(user.get('balance', 0) for user in user_data.values())
        
        # Активные за последние 7 дней
        week_ago = datetime.now().timestamp() - 7 * 24 * 60 * 60
        active_week = sum(1 for user in user_data.values() 
                         if user.get('last_activity') and 
                         datetime.fromisoformat(user['last_activity']).timestamp() > week_ago)
        
        stats_text = Styles.ADMIN.format(text="СТАТИСТИКА") + f"""

👥 *Всего пользователей:* {total_users}
📝 *Всего отзывов:* {total_reviews}
💰 *Общий баланс:* {total_balance}₽
🟢 *Активных за неделю:* {active_week}

📈 *Топ по балансу:*
"""
        
        # Топ по балансу
        top_users = sorted(user_data.items(), key=lambda x: x[1].get('balance', 0), reverse=True)[:5]
        for i, (uid, data) in enumerate(top_users, 1):
            try:
                user_chat = await context.bot.get_chat(int(uid))
                username = f"@{user_chat.username}" if user_chat.username else user_chat.first_name
                stats_text += f"{i}. {username}: {data.get('balance', 0)}₽\n"
            except:
                stats_text += f"{i}. User{uid}: {data.get('balance', 0)}₽\n"
        
        await query.edit_message_text(
            stats_text,
            reply_markup=get_admin_keyboard(user_id),
            parse_mode='Markdown'
        )
    
    elif query.data == "admin_broadcast":
        if not is_admin(user_id):
            return
        
        user_data[str(user_id)]['state'] = WAITING_BROADCAST
        save_data()
        
        await query.edit_message_text(
            "📢 *Введите сообщение для рассылки:*\n\n(Поддерживается Markdown форматирование)",
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "admin_channels":
        # Только владелец может управлять каналами
        if not is_owner(user_id):
            await query.edit_message_text("❌ Только владелец может управлять каналами!")
            return
        
        channels_text = Styles.OWNER.format(text="УПРАВЛЕНИЕ КАНАЛАМИ") + "\n\n"
        channels_text += "*Текущие каналы:*\n"
        for channel in bot_settings["required_channels"]:
            channels_text += f"• {channel}\n"
        
        await query.edit_message_text(
            channels_text,
            reply_markup=get_channels_keyboard(user_id),
            parse_mode='Markdown'
        )
    
    elif query.data == "admin_manage":
        # Только владелец может управлять админами
        if not is_owner(user_id):
            await query.edit_message_text("❌ Только владелец может управлять админами!")
            return
        
        admin_text = Styles.OWNER.format(text="УПРАВЛЕНИЕ АДМИНАМИ") + "\n\n"
        admin_text += "*Текущие админы:*\n"
        for admin_id in bot_settings["admin_ids"]:
            role = "👑 Владелец" if admin_id == bot_settings["owner_id"] else "⚡ Админ"
            admin_text += f"• {role} {admin_id}\n"
        
        await query.edit_message_text(
            admin_text,
            reply_markup=get_admin_manage_keyboard(user_id),
            parse_mode='Markdown'
        )
    
    elif query.data == "add_channel":
        # Только владелец может добавлять каналы
        if not is_owner(user_id):
            await query.edit_message_text("❌ Только владелец может добавлять каналы!")
            return
        
        user_data[str(user_id)]['state'] = WAITING_CHANNEL_ADD
        save_data()
        
        await query.edit_message_text(
            "📢 *Введите username канала (например: @channelname):*",
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "add_admin":
        # Только владелец может добавлять админов
        if not is_owner(user_id):
            await query.edit_message_text("❌ Только владелец может добавлять админов!")
            return
        
        user_data[str(user_id)]['state'] = WAITING_ADMIN_ADD
        save_data()
        
        await query.edit_message_text(
            "👑 *Введите ID пользователя для добавления в админы:*",
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("remove_channel_"):
        # Только владелец может удалять каналы
        if not is_owner(user_id):
            await query.edit_message_text("❌ Только владелец может удалять каналы!")
            return
        
        channel_to_remove = query.data.replace("remove_channel_", "")
        if channel_to_remove in bot_settings["required_channels"]:
            bot_settings["required_channels"].remove(channel_to_remove)
            save_data()
        
        await query.edit_message_text(
            f"✅ Канал {channel_to_remove} удален!",
            reply_markup=get_channels_keyboard(user_id),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("remove_admin_"):
        # Только владелец может удалять админов
        if not is_owner(user_id):
            await query.edit_message_text("❌ Только владелец может удалять админов!")
            return
        
        admin_to_remove = int(query.data.replace("remove_admin_", ""))
        # Нельзя удалить владельца
        if admin_to_remove == bot_settings["owner_id"]:
            await query.edit_message_text(
                "❌ Нельзя удалить владельца!",
                reply_markup=get_admin_manage_keyboard(user_id),
                parse_mode='Markdown'
            )
            return
            
        if admin_to_remove in bot_settings["admin_ids"]:
            bot_settings["admin_ids"].remove(admin_to_remove)
            save_data()
        
        await query.edit_message_text(
            f"✅ Админ {admin_to_remove} удален!",
            reply_markup=get_admin_manage_keyboard(user_id),
            parse_mode='Markdown'
        )
    
    elif query.data == "owner_cannot_remove":
        await query.answer("❌ Владельца нельзя удалить!", show_alert=True)
    
    elif query.data in ["withdraw_sbp", "withdraw_card", "withdraw_crypto"]:
        # Проверяем условия вывода
        can_withdraw, conditions = check_withdraw_conditions(user_id)
        
        if not can_withdraw:
            await query.edit_message_text(
                f"❌ *Не выполнены условия вывода!*\n\n{chr(10).join(conditions)}",
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        balance = user_data.get(str(user_id), {}).get('balance', 0)
        
        method_map = {
            "withdraw_sbp": "СБП",
            "withdraw_card": "Банковская карта", 
            "withdraw_crypto": "Crypto Bot"
        }
        
        user_data[str(user_id)]['withdraw_method'] = method_map[query.data]
        user_data[str(user_id)]['state'] = WAITING_WITHDRAW_AMOUNT
        save_data()
        
        withdraw_amount_text = Styles.BLUE_SUBTITLE.format(text="ЗАЯВКА НА ВЫВОД") + f"""

💎 *Способ вывода:* {method_map[query.data]}
💰 *Доступный баланс:* {balance}₽
🎯 *Минимальная сумма:* {bot_settings.get('min_withdraw_amount', 10)}₽

👇 *Напишите сумму для вывода в рублях:*
        """
        
        await query.edit_message_text(
            withdraw_amount_text,
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "back_to_main":
        user_info = user_data.get(str(user_id), {})
        can_withdraw, conditions = check_withdraw_conditions(user_id)
        
        welcome_text = f"""
🎉 *Главное меню* 🎉

💎 *Ваш баланс:* {user_info.get('balance', 0)}₽
👥 *Рефералов:* {len(user_info.get('referrals', []))}
📝 *Отзывов:* {user_info.get('reviews_count', 0)}

📋 *Условия вывода:*
{chr(10).join(conditions)}

{'✅ *Вывод доступен!*' if can_withdraw else '❌ *Вывод пока недоступен*'}
        """
        
        keyboard = get_main_keyboard()
        if is_admin(user_id):
            keyboard.inline_keyboard.append([InlineKeyboardButton("👑 Админ Панель", callback_data="admin_panel")])
        
        await query.edit_message_text(
            welcome_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

# Обработка сообщений пользователя
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message_text = update.message.text
    
    # Обновляем время активности
    if str(user_id) in user_data:
        user_data[str(user_id)]['last_activity'] = datetime.now().isoformat()
        save_data()
    
    # Проверка подписки при любом сообщении (только для не-админов)
    if not is_admin(user_id):
        is_subscribed, channel = await check_subscription(user_id, context)
        if not is_subscribed:
            await update.message.reply_text(
                f"❌ Для использования бота необходимо подписаться на канал: {channel}\n\nИспользуйте /start",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{channel[1:]}")]])
            )
            return
    
    if str(user_id) not in user_data:
        await start(update, context)
        return
    
    current_state = user_data[str(user_id)].get('state')
    
    # Админ: рассылка
    if current_state == WAITING_BROADCAST and is_admin(user_id):
        await update.message.reply_text("📢 *Начинаю рассылку...*", parse_mode='Markdown')
        
        success = 0
        failed = 0
        total = len(user_data)
        
        for uid in user_data:
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=message_text,
                    parse_mode='Markdown'
                )
                success += 1
                await asyncio.sleep(0.1)  # Задержка чтобы не превысить лимиты
            except Exception as e:
                failed += 1
        
        user_data[str(user_id)]['state'] = None
        save_data()
        
        await update.message.reply_text(
            f"✅ *Рассылка завершена!*\n\n📊 Статистика:\n• Успешно: {success}\n• Не удалось: {failed}\n• Всего: {total}",
            reply_markup=get_admin_keyboard(user_id),
            parse_mode='Markdown'
        )
        return
    
    # Владелец: добавление канала
    elif current_state == WAITING_CHANNEL_ADD and is_owner(user_id):
        if message_text.startswith('@'):
            if message_text not in bot_settings["required_channels"]:
                bot_settings["required_channels"].append(message_text)
                save_data()
                await update.message.reply_text(
                    f"✅ Канал {message_text} добавлен!",
                    reply_markup=get_admin_keyboard(user_id)
                )
            else:
                await update.message.reply_text(
                    "❌ Этот канал уже в списке!",
                    reply_markup=get_admin_keyboard(user_id)
                )
        else:
            await update.message.reply_text(
                "❌ Неверный формат! Используйте @username",
                reply_markup=get_admin_keyboard(user_id)
            )
        
        user_data[str(user_id)]['state'] = None
        save_data()
        return
    
    # Владелец: добавление админа
    elif current_state == WAITING_ADMIN_ADD and is_owner(user_id):
        try:
            new_admin_id = int(message_text)
            if new_admin_id not in bot_settings["admin_ids"]:
                bot_settings["admin_ids"].append(new_admin_id)
                save_data()
                await update.message.reply_text(
                    f"✅ Пользователь {new_admin_id} добавлен в админы!",
                    reply_markup=get_admin_keyboard(user_id)
                )
            else:
                await update.message.reply_text(
                    "❌ Этот пользователь уже админ!",
                    reply_markup=get_admin_keyboard(user_id)
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Введите корректный ID пользователя!",
                reply_markup=get_admin_keyboard(user_id)
            )
        
        user_data[str(user_id)]['state'] = None
        save_data()
        return
    
    # Обычный процесс оставления отзыва (остальной код остается прежним)
    # ... [ваш существующий код обработки отзывов и вывода] ...

# Основная функция
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🔷 Бот запущен с системой прав владельца!")
    print(f"👑 Владелец: {bot_settings['owner_id']}")
    print(f"⚡ Админы: {bot_settings['admin_ids']}")
    print(f"💰 Условия вывода: {bot_settings.get('min_withdraw_amount', 10)}₽ + {bot_settings.get('min_referrals_for_withdraw', 1)} реферал")
    print("🔐 Только владелец может управлять каналами и админами")
    application.run_polling()

if __name__ == "__main__":
    main()
