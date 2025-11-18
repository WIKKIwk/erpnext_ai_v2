from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import BotConfig, load_bot_config
from .erpnext_client import ERPNextClient, ERPNextError
from .storage import BotStorage

logger = logging.getLogger(__name__)


ORDER_PHOTO, ORDER_PHONE, ORDER_NOTES, ORDER_QTY, ORDER_UNIT = range(5)


def build_member_label(user: Tuple[int, Optional[str], Optional[str]]) -> str:
    telegram_id, username, full_name = user
    if full_name:
        label = full_name
    elif username:
        label = f"@{username}"
    else:
        label = str(telegram_id)
    return label


@dataclass
class OrderDraft:
    chat_id: int
    requester_id: int
    requester_name: str
    photo_path: Optional[Path] = None
    photo_caption: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None


class SalesBot:
    """Telegram bot orchestrating ERPNext integrations."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.storage = BotStorage(config.db_path, config.encryption_key)
        self.erpnext = ERPNextClient(config)
        self.application = (
            Application.builder()
            .token(config.token)
            .rate_limiter(AIORateLimiter())
            .post_init(self._post_init)
            .build()
        )
        self._register_handlers()

    async def _post_init(self, application: Application) -> None:
        bot = application.bot
        me = await bot.get_me()
        logger.info("Connected to Telegram as %s (@%s)", me.full_name, me.username)

    def _register_handlers(self) -> None:
        app = self.application
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("help", self.handle_help))
        app.add_handler(CommandHandler("add_master_manager", self.handle_add_master_manager))
        app.add_handler(CommandHandler("remove_master_manager", self.handle_remove_master_manager))
        app.add_handler(CommandHandler("list_master_managers", self.handle_list_master_managers))
        app.add_handler(CommandHandler("users", self.handle_list_group_users))
        app.add_handler(CommandHandler("report", self.handle_report))
        app.add_handler(CommandHandler("set_api", self.handle_set_api_credentials))
        app.add_handler(CommandHandler("whoami", self.handle_whoami))

        order_conversation = ConversationHandler(
            entry_points=[CommandHandler("order", self.handle_order_start)],
            states={
                ORDER_PHOTO: [
                    MessageHandler(filters.PHOTO, self.handle_order_photo),
                    CommandHandler("skip", self.handle_order_skip_photo),
                ],
                ORDER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_order_phone)],
                ORDER_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_order_notes)],
                ORDER_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_order_quantity)],
                ORDER_UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_order_unit)],
            },
            fallbacks=[CommandHandler("cancel", self.handle_order_cancel)],
            allow_reentry=True,
            per_chat=True,
            per_user=True,
            name="sales_order_flow",
        )
        app.add_handler(order_conversation)

        app.add_handler(CallbackQueryHandler(self.handle_assign_sales_manager, pattern=r"^assign_sm:"))

        app.add_handler(
            MessageHandler(
                filters.ChatType.GROUPS & (~filters.COMMAND),
                self.handle_group_activity,
            )
        )
        app.add_error_handler(self.handle_error)

    # --------------------------------------------------------------------- utils
    def _is_admin(self, user_id: int) -> bool:
        return user_id in self.config.admin_ids

    async def _send_dm(self, user_id: int, text: str, *, parse_mode: Optional[str] = None) -> bool:
        try:
            await self.application.bot.send_message(chat_id=user_id, text=text, parse_mode=parse_mode)
        except Forbidden:
            return False
        return True

    def _get_order_draft(self, context: ContextTypes.DEFAULT_TYPE) -> Optional[OrderDraft]:
        draft = context.user_data.get("order_draft")
        if isinstance(draft, OrderDraft):
            return draft
        return None

    def _set_order_draft(self, context: ContextTypes.DEFAULT_TYPE, draft: OrderDraft) -> None:
        context.user_data["order_draft"] = draft

    def _clear_order_draft(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        draft = context.user_data.pop("order_draft", None)
        if isinstance(draft, OrderDraft) and draft.photo_path and draft.photo_path.exists():
            try:
                draft.photo_path.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------- handlers
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or not user:
            return
        name = user.full_name or (f"@{user.username}" if user.username else str(user.id))

        if chat.type == ChatType.PRIVATE:
            if self._is_admin(user.id):
                text = (
                    "Salom administrator!\n\n"
                    "🔹 Sales master manager qo'shish uchun: `/add_master_manager <telegram_id>`\n"
                    "🔹 Ro'yxatni ko'rish uchun: `/list_master_managers`\n"
                    "🔹 O'chirish: `/remove_master_manager <telegram_id>`\n\n"
                    "Botni guruhlarga admin sifatida qo'shganingizga ishonch hosil qiling."
                )
            elif self.storage.is_master_manager(user.id):
                text = (
                    "Salom Sales Master Manager!\n\n"
                    "Guruhingizda `/users` commandini yuboring va kerakli a'zoni tanlab sales manager qilib tayinlang.\n"
                    "Tayinlangandan so'ng bot avtomatik ravishda foydalanuvchiga shaxsiy chatda xabar yuboradi."
                )
            else:
                manager = self.storage.get_sales_manager(user.id)
                if manager:
                    status = manager["status"]
                    if status == "awaiting_api":
                        text = (
                            "Siz sales manager sifatida tayinlandingiz.\n"
                            "ERPNext API kalit va secret yuborish uchun quyidagidan foydalaning:\n"
                            "`/set_api <api_key> <api_secret>`"
                        )
                    elif status == "active":
                        text = "Sales manager sifatida tayinlangan guruhingizda /report va buyurtmalarni boshqarishingiz mumkin."
                    else:
                        text = f"Sales manager holati: {status}"
                else:
                    text = (
                        f"Salom {name}!\n"
                        "Bu bot orqali buyurtmalar yuborish va hisobotlar olish mumkin.\n"
                        "Guruhda `/report` yoki `/order` commandlarini sinab ko'ring."
                    )
            await context.bot.send_message(chat_id=chat.id, text=text, parse_mode=ParseMode.MARKDOWN)
            return

        # Group start
        self.storage.touch_group(chat.id, chat.title)
        greeting = (
            f"Assalomu alaykum {chat.title or 'guruh'}!\n"
            "Adminlar va sales master managerlar uchun qo'llanma:\n"
            "- `/users` orqali foydalanuvchilar ro'yxatini oling\n"
            "- `/report` bilan oxirgi buyurtmalar hisobotini ko'ring\n"
            "- `/order` buyurtma yuborish jarayonini boshlaydi"
        )
        await update.message.reply_text(greeting)

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if not chat:
            return
        help_text = (
            "Asosiy buyruqlar:\n"
            "• `/report` — guruh sales manager'ining ERPNext hisobotini chiqaradi\n"
            "• `/order` — yangi buyurtma yaratish jarayonini boshlaydi\n"
            "• `/users` — faqat Sales Master Manager uchun, guruh a'zolarini ko'rsatadi\n"
            "• `/set_api <api_key> <api_secret>` — sales manager shaxsiy chatida API kalitlarini kiritadi\n"
            "• `/whoami` — hozirgi foydalanuvchi va guruh haqidagi ma'lumot"
        )
        await update.message.reply_text(help_text)

    async def handle_add_master_manager(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not self._is_admin(user.id):
            await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
            return
        if not context.args:
            await update.message.reply_text("Foydalanish: /add_master_manager <telegram_id>")
            return
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Telegram ID faqat sonlardan iborat bo'lishi kerak.")
            return
        name_hint = context.args[1] if len(context.args) > 1 else None
        created = self.storage.add_master_manager(
            target_id,
            full_name=name_hint,
            username=None,
            added_by=user.id,
        )
        if created:
            await update.message.reply_text(f"{target_id} Sales Master Manager sifatida qo'shildi.")
            await self._send_dm(
                target_id,
                "Siz sales master manager sifatida tayinlandingiz. Guruhingizda `/users` buyruqni ishlating.",
            )
        else:
            await update.message.reply_text(f"{target_id} allaqachon ro'yxatdan o'tgan, ma'lumot yangilandi.")

    async def handle_remove_master_manager(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not self._is_admin(user.id):
            await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
            return
        if not context.args:
            await update.message.reply_text("Foydalanish: /remove_master_manager <telegram_id>")
            return
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Telegram ID faqat sonlardan iborat bo'lishi kerak.")
            return
        self.storage.remove_master_manager(target_id)
        await update.message.reply_text(f"{target_id} ro'yxatdan o'chirildi.")

    async def handle_list_master_managers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not self._is_admin(user.id):
            await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
            return
        rows = self.storage.list_master_managers()
        if not rows:
            await update.message.reply_text("Sales master managerlar ro'yxati bo'sh.")
            return
        lines = ["Ro'yxat:"]
        for row in rows:
            parts = [str(row["telegram_id"])]
            if row["full_name"]:
                parts.append(row["full_name"])
            if row["username"]:
                parts.append(f"@{row['username']}")
            lines.append(" - " + " | ".join(parts))
        await update.message.reply_text("\n".join(lines))

    async def handle_list_group_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP) or not user:
            await update.message.reply_text("Bu buyruq faqat guruhda ishlaydi.")
            return
        if not self.storage.is_master_manager(user.id):
            await update.message.reply_text("Siz sales master manager ro'yxatida emassiz.")
            return

        self.storage.touch_group(chat.id, chat.title)
        self.storage.assign_group_to_master(chat.id, user.id)

        members = self.storage.list_group_members(chat.id)
        if not members:
            await update.message.reply_text(
                "Hozircha foydalanuvchilar ro'yxati bo'sh. Bot faqat yozgan foydalanuvchilarni qayd qiladi."
            )
            return

        keyboard_rows = []
        for member in members[:20]:  # limit to 20 buttons
            label_parts = []
            if member["full_name"]:
                label_parts.append(member["full_name"])
            elif member["username"]:
                label_parts.append(f"@{member['username']}")
            else:
                label_parts.append(str(member["telegram_id"]))
            label = " ".join(label_parts)
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"assign_sm:{chat.id}:{member['telegram_id']}",
                    )
                ]
            )
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        await update.message.reply_text(
            "Sales manager qilib tayinlamoqchi bo'lgan foydalanuvchini tanlang:",
            reply_markup=keyboard,
        )

    async def handle_assign_sales_manager(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        user = query.from_user
        data = query.data or ""
        try:
            _, chat_id_raw, member_id_raw = data.split(":")
            chat_id = int(chat_id_raw)
            member_id = int(member_id_raw)
        except (ValueError, AttributeError):
            await query.edit_message_text("Noto'g'ri format.")
            return

        if not self.storage.is_master_manager(user.id):
            await query.edit_message_text("Siz sales master manager emassiz.")
            return

        chat = query.message.chat if query.message else None
        chat_title = chat.title if chat else ""
        try:
            member = await context.bot.get_chat_member(chat_id, member_id)
        except Exception:  # noqa: BLE001
            await query.edit_message_text("Tanlangan foydalanuvchini topib bo'lmadi.")
            return
        if member.user.is_bot:
            await query.edit_message_text("Botni sales manager qilib tayinlab bo'lmaydi.")
            return

        try:
            self.storage.assign_sales_manager(
                telegram_id=member_id,
                group_chat_id=chat_id,
                username=member.user.username,
                full_name=member.user.full_name,
            )
        except ValueError as exc:
            await query.edit_message_text(str(exc))
            return

        sm_text = (
            "🎉 Siz sales manager sifatida tayinlandingiz!\n\n"
            "ERPNext API kalit va secret yuborish uchun shaxsiy chatda quyidagidan foydalaning:\n"
            "`/set_api <api_key> <api_secret>`\n\n"
            "Kalitlar tekshirilgandan so'ng guruh foydalanuvchilari `/report` va `/order` dan foydalanishi mumkin bo'ladi."
        )
        delivered = await self._send_dm(member_id, sm_text, parse_mode=ParseMode.MARKDOWN)
        if delivered:
            await query.edit_message_text(
                f"{member.user.full_name or member.user.username} sales manager sifatida tayinlandi."
            )
        else:
            await query.edit_message_text(
                "Foydalanuvchi sales manager bo'ldi, ammo shaxsiy xabar yuborilmadi. "
                "Iltimos ular botga /start yuborishlarini eslatib qo'ying."
            )

        self.storage.touch_group(chat_id, chat_title)

    async def handle_set_api_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or chat.type != ChatType.PRIVATE or not user:
            await update.message.reply_text("API kalitlarni faqat shaxsiy chatda yuboring.")
            return
        if len(context.args) < 2:
            await update.message.reply_text("Foydalanish: /set_api <api_key> <api_secret>")
            return
        api_key = context.args[0].strip()
        api_secret = context.args[1].strip()
        manager = self.storage.get_sales_manager(user.id)
        if not manager:
            await update.message.reply_text("Siz sales manager sifatida tayinlanmagansiz.")
            return
        group_chat_id = manager["group_chat_id"]
        status = "awaiting_api"
        ok, reason = self.erpnext.validate_credentials(api_key, api_secret)
        if ok:
            status = "active"
            result_text = f"✅ Kalitlar tasdiqlandi: {reason}"
        else:
            result_text = f"❌ Kalitlar tasdiqlanmadi: {reason}\nIltimos qayta urinib ko'ring."
        self.storage.store_sales_manager_credentials(
            telegram_id=user.id,
            api_key=api_key,
            api_secret=api_secret,
            status=status,
        )
        await update.message.reply_text(result_text)
        if ok:
            await self.application.bot.send_message(
                chat_id=group_chat_id,
                text=f"{user.full_name or user.username} ERPNext bilan muvaffaqiyatli bog'landi.",
            )

    async def handle_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await update.message.reply_text("Hisobotni faqat guruhda so'rash mumkin.")
            return
        credentials = self.storage.get_group_credentials(chat.id)
        if not credentials:
            await update.message.reply_text(
                "Bu guruh uchun hali sales manager tayinlanmagan yoki API kalitlari kiritilmagan."
            )
            return
        manager_id, api_key, api_secret, status = credentials
        if status != "active":
            await update.message.reply_text("Sales manager API kalitlarini hali tasdiqlamagan.")
            return
        try:
            rows = self.erpnext.fetch_report(
                api_key=api_key,
                api_secret=api_secret,
                settings=self.config.report,
            )
        except ERPNextError as exc:
            await update.message.reply_text(f"Hisobotni olishda xatolik: {exc}")
            return
        if not rows:
            await update.message.reply_text("ERPNext hisobotida ma'lumot topilmadi.")
            return
        lines = ["📊 Oxirgi buyurtmalar hisobotidan parchalar:"]
        fields = self.config.report.fields or list(rows[0].keys())
        for idx, row in enumerate(rows, start=1):
            item_lines = [f"{idx}. {row.get('name', 'N/A')}"]
            for field in fields:
                if field == "name":
                    continue
                value = row.get(field)
                if value is None:
                    continue
                item_lines.append(f"   • {field}: {value}")
            lines.append("\n".join(item_lines))
        await update.message.reply_text("\n\n".join(lines))

    async def handle_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or not user:
            return
        lines = [
            f"User: {user.full_name or user.username or user.id}",
            f"User ID: {user.id}",
            f"Chat: {chat.title or chat.full_name or chat.id}",
            f"Chat ID: {chat.id}",
            f"Chat type: {chat.type}",
        ]
        manager = self.storage.get_sales_manager(user.id)
        if manager:
            lines.append(f"Sales manager status: {manager['status']}")
            lines.append(f"Tayinlangan chat: {manager['group_chat_id']}")
        await update.message.reply_text("\n".join(lines))

    # ---------------------------------------------------------------- order flow
    async def handle_order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP) or not user:
            await update.message.reply_text("Buyurtma faqat guruhda boshlanadi.")
            return ConversationHandler.END

        credentials = self.storage.get_group_credentials(chat.id)
        if not credentials:
            await update.message.reply_text("Bu guruh uchun sales manager tayinlanmagan.")
            return ConversationHandler.END
        _, _, _, status = credentials
        if status != "active":
            await update.message.reply_text("Sales manager API kalitlarini hali tasdiqlamagan.")
            return ConversationHandler.END

        draft = OrderDraft(
            chat_id=chat.id,
            requester_id=user.id,
            requester_name=user.full_name or user.username or str(user.id),
        )
        self._set_order_draft(context, draft)

        await update.message.reply_text(
            "📥 Buyurtma qabul qilindi. Iltimos tovar rasmini yuboring yoki `/skip` deb yozing.",
            reply_markup=None,
        )
        return ORDER_PHOTO

    async def handle_order_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = self._get_order_draft(context)
        if not draft or not update.message:
            return ConversationHandler.END
        photo = update.message.photo[-1]
        file = await photo.get_file()
        tmp_dir = Path(tempfile.gettempdir())
        file_path = tmp_dir / f"order_{draft.chat_id}_{draft.requester_id}_{file.file_unique_id}.jpg"
        await file.download_to_drive(file_path)
        draft.photo_path = file_path
        draft.photo_caption = update.message.caption
        self._set_order_draft(context, draft)
        await update.message.reply_text("📞 Telefon raqamini kiriting:")
        return ORDER_PHONE

    async def handle_order_skip_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("📞 Telefon raqamini kiriting:")
        return ORDER_PHONE

    async def handle_order_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = self._get_order_draft(context)
        if not draft:
            return ConversationHandler.END
        draft.phone = update.message.text.strip()
        self._set_order_draft(context, draft)
        await update.message.reply_text("ℹ️ Qo'shimcha ma'lumot yoki talabni kiriting (masalan, mahsulot turi):")
        return ORDER_NOTES

    async def handle_order_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = self._get_order_draft(context)
        if not draft:
            return ConversationHandler.END
        draft.notes = update.message.text.strip()
        self._set_order_draft(context, draft)
        await update.message.reply_text("🔢 Miqdorini kiriting:")
        return ORDER_QTY

    async def handle_order_quantity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = self._get_order_draft(context)
        if not draft:
            return ConversationHandler.END
        draft.quantity = update.message.text.strip()
        self._set_order_draft(context, draft)
        await update.message.reply_text("📏 O'lchov birligini kiriting (kg, dona va hokazo):")
        return ORDER_UNIT

    async def handle_order_unit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = self._get_order_draft(context)
        if not draft:
            return ConversationHandler.END
        draft.unit = update.message.text.strip()
        self._set_order_draft(context, draft)

        summary_lines = [
            "✅ Buyurtma ma'lumotlari:",
            f"- Telefon: {draft.phone}",
            f"- Tavsif: {draft.notes}",
            f"- Miqdor: {draft.quantity} {draft.unit}",
        ]
        await update.message.reply_text("\n".join(summary_lines) + "\n\nERPNext ga yuborilmoqda...")

        credentials = self.storage.get_group_credentials(draft.chat_id)
        if not credentials:
            await update.message.reply_text("Sales manager ma'lumotlari topilmadi.")
            self._clear_order_draft(context)
            return ConversationHandler.END
        manager_id, api_key, api_secret, status = credentials
        if status != "active":
            await update.message.reply_text("Sales manager API kalitlari tasdiqlanmagan.")
            self._clear_order_draft(context)
            return ConversationHandler.END

        notes = (
            f"Telegram foydalanuvchisi: {draft.requester_name} ({draft.requester_id})\n"
            f"Guruh: {draft.chat_id}\n"
            f"Telefon: {draft.phone}\n"
            f"Tavsif: {draft.notes}\n"
            f"Miqdor: {draft.quantity} {draft.unit}"
        )
        try:
            lead_response = self.erpnext.create_lead(
                api_key=api_key,
                api_secret=api_secret,
                order_settings=self.config.order,
                lead_name=draft.requester_name,
                phone=draft.phone,
                notes=notes,
            )
        except ERPNextError as exc:
            await update.message.reply_text(f"ERPNext ga saqlashda xatolik: {exc}")
            self._clear_order_draft(context)
            return ConversationHandler.END

        attachment_link = None
        if draft.photo_path and self.config.order.attach_order_photo:
            try:
                upload = self.erpnext.upload_file(
                    api_key=api_key,
                    api_secret=api_secret,
                    file_name=draft.photo_path.name,
                    file_path=draft.photo_path,
                    attach_to_doctype=self.config.order.target_doctype,
                    attach_to_name=lead_response.get("data", {}).get("name")
                    if isinstance(lead_response, dict)
                    else None,
                )
                attachment_link = upload.get("message", {}).get("file_url")
            except ERPNextError as exc:
                await update.message.reply_text(f"Rasmni yuklashning imkoni bo'lmadi: {exc}")

        order_payload: Dict[str, object] = {
            "lead": lead_response,
            "phone": draft.phone,
            "notes": draft.notes,
            "quantity": draft.quantity,
            "unit": draft.unit,
            "attachment": attachment_link,
        }
        order_id = self.storage.log_order_request(
            chat_id=draft.chat_id,
            requester_id=draft.requester_id,
            payload=order_payload,
            sales_manager_id=manager_id,
            status="created",
        )

        await update.message.reply_text(f"✅ Buyurtma ERPNext ga yuborildi. ID: {order_id}")
        await self.application.bot.send_message(
            chat_id=manager_id,
            text=(
                "Yangi buyurtma kelib tushdi.\n"
                f"Foydalanuvchi: {draft.requester_name}\n"
                f"Telefon: {draft.phone}\n"
                f"Miqdor: {draft.quantity} {draft.unit}"
            ),
        )
        self._clear_order_draft(context)
        return ConversationHandler.END

    async def handle_order_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Buyurtma bekor qilindi.")
        self._clear_order_draft(context)
        return ConversationHandler.END

    # ------------------------------------------------------------- misc tracking
    async def handle_group_activity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or user.is_bot or not message:
            return
        self.storage.touch_group(chat.id, chat.title)
        preview = message.text[:120] if message.text else None
        self.storage.upsert_group_member(
            chat.id,
            telegram_id=user.id,
            username=user.username,
            full_name=user.full_name,
            message_preview=preview,
        )

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Unhandled error in Telegram bot: %s", context.error, exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("Botda kutilmagan xatolik yuz berdi.")

    # ------------------------------------------------------------------- runtime
    def run_polling(self) -> None:
        logging.basicConfig(
            level=os.getenv("TELEGRAM_LOG_LEVEL", "INFO"),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logger.info("Starting Telegram sales bot...")
        self.application.run_polling(drop_pending_updates=True)


def main() -> None:
    config = load_bot_config()
    bot = SalesBot(config)
    bot.run_polling()


if __name__ == "__main__":
    main()
