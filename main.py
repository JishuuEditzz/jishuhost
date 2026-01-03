import os
import json
import asyncio
import random
import logging
import re
from pathlib import Path
from typing import List, Union, Optional, Dict

from pyrogram import Client, filters, enums
from pyrogram.types import Message, User
from pyrogram.errors import (
    FloodWait, PeerIdInvalid, UsernameInvalid,
    UsernameNotOccupied, ChatWriteForbidden,
    UserNotParticipant, ChannelPrivate, ChatAdminRequired,
    MessageDeleteForbidden
)

# Bot developer info
BOT_DEVELOPER_ID = 5265190519  # JishuEdits User ID
BOT_DEVELOPER_USERNAME = "JishuEdits"  # JishuEdits username

# Configuration file
CONFIG_FILE = "config.json"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_env_file():
    """Load environment variables from .env file with comma-separated format"""
    env_file = Path(".env")
    if not env_file.exists():
        logger.error(".env file not found!")
        return False
    
    try:
        with open(env_file, 'r') as f:
            content = f.read().strip()
        
        # Parse comma-separated format: API_ID=22207xx, API_HASH=hash, BOT_TOKEN=token, OWNER_ID=694924xxx
        env_vars = {}
        for match in re.finditer(r'(\w+)=([^,\s]+)', content):
            key, value = match.groups()
            env_vars[key] = value
            os.environ[key] = value
        
        logger.info(f"Loaded {len(env_vars)} environment variables")
        return True
        
    except Exception as e:
        logger.error(f"Error loading .env file: {e}")
        return False

# Load environment variables
if not load_env_file():
    logger.warning("Using system environment variables instead")

# Configuration from environment
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

class BotConfig:
    """Handles configuration loading and saving"""
    
    DEFAULT_CONFIG = {
        "authorized_users": [], # List of user IDs
        "authorized_chats": [], # List of chat IDs
        "spam_command": "/s",
        "spam_messages": ["Hello {mention}! Welcome to the group!"],
        "owner_id": OWNER_ID,
        "user_secret_codes": {} # Dictionary: {secret_code: user_id}
    }
    
    def __init__(self):
        self.config = self.load_config()
        # Ensure owner is in the authorized list on startup
        if self.config["owner_id"] not in self.config["authorized_users"]:
            self.config["authorized_users"].append(self.config["owner_id"])
            self.save_config()
            logger.info(f"Owner ID {self.config['owner_id']} added to authorized users on startup.")
        
    def load_config(self) -> dict:
        """Load configuration from file or create default"""
        if Path(CONFIG_FILE).exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return self.DEFAULT_CONFIG.copy()
        return self.DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """Save configuration to file"""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    @property
    def authorized_users(self) -> List[int]:
        return self.config.get("authorized_users", [])
    
    @authorized_users.setter
    def authorized_users(self, users: List[int]):
        self.config["authorized_users"] = users
        self.save_config()
    
    @property
    def authorized_chats(self) -> List[int]:
        return self.config.get("authorized_chats", [])
    
    @authorized_chats.setter
    def authorized_chats(self, chats: List[int]):
        self.config["authorized_chats"] = chats
        self.save_config()
    
    @property
    def spam_command(self) -> str:
        return self.config.get("spam_command", "/s")
    
    @spam_command.setter
    def spam_command(self, command: str):
        if not command.startswith('/'):
            command = f'/{command}'
        self.config["spam_command"] = command
        self.save_config()
    
    @property
    def spam_messages(self) -> List[str]:
        return self.config.get("spam_messages", ["Hello {mention}! Welcome to the group!"])
    
    @spam_messages.setter
    def spam_messages(self, messages: List[str]):
        self.config["spam_messages"] = messages
        self.save_config()
    
    @property
    def user_secret_codes(self) -> Dict[str, int]:
        return self.config.get("user_secret_codes", {})
    
    @user_secret_codes.setter
    def user_secret_codes(self, codes: Dict[str, int]):
        self.config["user_secret_codes"] = codes
        self.save_config()
    
    def add_spam_message(self, message: str):
        """Add a new spam message to the list"""
        messages = self.spam_messages
        if message not in messages:
            messages.append(message)
            self.spam_messages = messages
    
    def remove_spam_message(self, index: int):
        """Remove a spam message by index"""
        messages = self.spam_messages
        if 0 <= index < len(messages):
            messages.pop(index)
            self.spam_messages = messages
    
    def add_authorized_chat(self, chat_id: int):
        """Add chat to authorized chats list"""
        chats = self.authorized_chats
        if chat_id not in chats:
            chats.append(chat_id)
            self.authorized_chats = chats
    
    def remove_authorized_chat(self, chat_id: int):
        """Remove chat from authorized chats list"""
        chats = self.authorized_chats
        if chat_id in chats:
            chats.remove(chat_id)
            self.authorized_chats = chats

    def add_authorized_user(self, user_id: int):
        """Add user to authorized users list"""
        users = self.authorized_users
        if user_id not in users and user_id != self.owner_id: # Don't add owner explicitly again
            users.append(user_id)
            self.authorized_users = users

    def remove_authorized_user(self, user_id: int):
        """Remove user from authorized users list"""
        users = self.authorized_users
        if user_id in users and user_id != self.owner_id: # Don't remove owner from the list
            users.remove(user_id)
            self.authorized_users = users

    def generate_secret_code(self, user_id: int) -> str:
        """Generate and store a unique secret code for a user."""
        import secrets
        code = secrets.token_urlsafe(16) # Generates a secure random URL-safe string
        codes = self.user_secret_codes
        # Ensure the code is unique (though highly unlikely to collide)
        while code in codes:
            code = secrets.token_urlsafe(16)
        codes[code] = user_id
        self.user_secret_codes = codes
        return code

    def get_user_id_from_code(self, code: str) -> Optional[int]:
        """Get the user ID associated with a secret code."""
        return self.user_secret_codes.get(code)

    def revoke_secret_code(self, code: str) -> bool:
        """Remove a secret code."""
        codes = self.user_secret_codes
        if code in codes:
            del codes[code]
            self.user_secret_codes = codes
            return True
        return False

    @property
    def owner_id(self) -> int:
        return self.config.get("owner_id", OWNER_ID)

# Initialize configuration
config = BotConfig()

# Initialize Pyrogram client
app = Client(
    "spam_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    parse_mode=enums.ParseMode.HTML
)

# Global variable to track current spam command
current_spam_command = config.spam_command

# Utility functions
async def resolve_user_id(user_input: str) -> Optional[int]:
    """Resolve username or user_id to user ID"""
    try:
        if user_input.isdigit() or (user_input.startswith('-') and user_input[1:].isdigit()):
            return int(user_input)
        
        if user_input.startswith('@'):
            user_input = user_input[1:]
        
        try:
            user = await app.get_users(user_input)
            return user.id
        except (UsernameInvalid, UsernameNotOccupied, PeerIdInvalid):
            return None
            
    except Exception as e:
        logger.error(f"Error resolving user ID {user_input}: {e}")
        return None

async def resolve_chat_id(chat_input: str) -> Optional[int]:
    """Resolve channel username or chat_id to chat ID"""
    try:
        if chat_input.isdigit() or (chat_input.startswith('-') and chat_input[1:].isdigit()):
            return int(chat_input)
        
        if chat_input.startswith('@'):
            chat_input = chat_input[1:]
        
        try:
            chat = await app.get_chat(chat_input)
            return chat.id
        except (UsernameInvalid, UsernameNotOccupied, PeerIdInvalid):
            return None
            
    except Exception as e:
        logger.error(f"Error resolving chat ID {chat_input}: {e}")
        return None

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized (explicitly in list or owner)"""
    return user_id in config.authorized_users

def is_owner(user_id: int) -> bool:
    """Check if user is the owner"""
    return user_id == config.owner_id

def is_chat_authorized(chat_id: int) -> bool:
    """Check if chat is authorized"""
    return chat_id in config.authorized_chats

def get_welcome_message(user_id: int) -> str:
    """Get appropriate welcome message based on user role"""
    
    spam_msgs_list = ""
    for idx, msg in enumerate(config.spam_messages[:5], 1):
        spam_msgs_list += f"{idx}. `{msg}`\n"
    if len(config.spam_messages) > 5:
        spam_msgs_list += f"and {len(config.spam_messages) - 5} more...\n"
    
    bot_by_footer = f'\n\n<b>Bot by:</b> <a href="tg://user?id={BOT_DEVELOPER_ID}">{BOT_DEVELOPER_USERNAME}</a> ❤️‍🔥'
    
    if is_owner(user_id):
        return f"""
<b>✨ Welcome to Spam Bot ✨</b>

<b>Owner:</b> <code>{config.owner_id}</code>
<b>Your ID:</b> <code>{user_id}</code>

<b>📋 Available Commands:</b>
• <code>{current_spam_command} &lt;your_secret_code&gt; &lt;target&gt; &lt;quantity&gt;</code> - Send spam messages (anonymous or non-anonymous)

<b>⚙️ Current Configuration:</b>
• Spam Command: <code>{current_spam_command}</code>
• Spam Messages: <code>{len(config.spam_messages)}</code> messages available
• Authorized Users: <code>{len(config.authorized_users)}</code>
• Authorized Chats: <code>{len(config.authorized_chats)}</code>
• Secret Codes Generated: <code>{len(config.user_secret_codes)}</code>

<b>📝 Spam Messages:</b>
{spam_msgs_list}

<b>🔧 Owner Commands (PM only):</b>
• <code>/a &lt;user_id/username&gt;</code> - Authorize user (adds to list)
• <code>/r &lt;user_id/username&gt;</code> - Remove user (removes from list)
• <code>/gensecret &lt;user_id/username&gt;</code> - Generate secret code for user
• <code>/revokesecret &lt;secret_code&gt;</code> - Revoke a secret code
• <code>/listauth</code> - List authorized users
• <code>/listcodes</code> - List user codes (user_id -> code)
• <code>/addchat &lt;chat_id_or_username&gt;</code> - Authorize chat (group/channel)
• <code>/removechat &lt;chat_id_or_username&gt;</code> - Remove authorized chat
• <code>/listchats</code> - List authorized chats
• <code>/setcmd &lt;new_command&gt;</code> - Set spam command
• <code>/addmsg &lt;message&gt;</code> - Add spam message
• <code>/delmsg &lt;index&gt;</code> - Delete spam message
• <code>/listmsg</code> - List all spam messages
• <code>/clrmsg</code> - Clear all spam messages

<b>📝 Usage:</b>
• Generate code for user: <code>/gensecret 123456789</code>
• User sends: <code>{current_spam_command} &lt;their_code&gt; @username 5</code>
{bot_by_footer}
        """
    elif is_authorized(user_id):
        # Try to find the user's code to display
        user_code = "Not Found"
        for code, uid in config.user_secret_codes.items():
            if uid == user_id:
                user_code = code
                break
        return f"""
<b>✨ Welcome to Spam Bot ✨</b>

<b>Your ID:</b> <code>{user_id}</code>
<b>Your Secret Code:</b> <code>{user_code}</code> (Share this only with the owner)

<b>📋 Available Commands:</b>
• <code>{current_spam_command} &lt;your_secret_code&gt; &lt;target&gt; &lt;quantity&gt;</code> - Send spam messages (anonymous or non-anonymous)

<b>⚙️ Current Configuration:</b>
• Spam Command: <code>{current_spam_command}</code>
• Spam Messages: <code>{len(config.spam_messages)}</code> messages available
• Your Status: <b>✅ Authorized User</b>

<b>📝 Usage:</b>
1. Add me to a group/channel as admin
2. Ask owner to authorize that chat using <code>/addchat</code>
3. Get your secret code from owner
4. Use: <code>{current_spam_command} &lt;your_code&gt; @username 5</code>

<i>Note: You can only use spam command in authorized chats.</i>
{bot_by_footer}
        """
    else:
        return f"""
<b>✨ Welcome to Spam Bot ✨</b>

<b>Your ID:</b> <code>{user_id}</code>

⛔ <b>Access Denied</b>

You are not authorized to use this bot.
Contact the owner (<code>{config.owner_id}</code>) for access.

<i>Owner can authorize you using: <code>/a {user_id}</code></i>
{bot_by_footer}
        """

# Command handlers
@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command with different access levels"""
    user_id = message.from_user.id
    welcome_message = get_welcome_message(user_id)
    await message.reply_text(welcome_message, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)

# Owner commands
@app.on_message(filters.command(["a", "add"]) & filters.private)
async def add_user_command(client: Client, message: Message):
    """Add user to authorized list (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/a &lt;user_id_or_username&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    
    user_input = message.command[1]
    user_id = await resolve_user_id(user_input)
    
    if not user_id:
        await message.reply_text("❌ Invalid user ID or username!")
        return
    
    if user_id == config.owner_id:
        await message.reply_text("✅ Owner is already authorized by default!")
        return

    config.add_authorized_user(user_id) # Use the new method
    
    await message.reply_text(f"✅ User <code>{user_id}</code> has been authorized!", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["r", "remove"]) & filters.private)
async def remove_user_command(client: Client, message: Message):
    """Remove user from authorized list (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/r &lt;user_id_or_username&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    
    user_input = message.command[1]
    user_id = await resolve_user_id(user_input)
    
    if not user_id:
        await message.reply_text("❌ Invalid user ID or username!")
        return
    
    if user_id == config.owner_id:
        await message.reply_text("❌ Cannot remove owner!")
        return

    if user_id not in config.authorized_users:
        await message.reply_text("⚠️ User is not in authorized list!")
        return

    config.remove_authorized_user(user_id) # Use the new method
    
    await message.reply_text(f"✅ User <code>{user_id}</code> has been removed!", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["gensecret"]) & filters.private)
async def generate_secret_command(client: Client, message: Message):
    """Generate a secret code for a user (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/gensecret &lt;user_id_or_username&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return

    user_input = message.command[1]
    user_id = await resolve_user_id(user_input)

    if not user_id:
        await message.reply_text("❌ Invalid user ID or username!")
        return

    if user_id not in config.authorized_users:
        await message.reply_text(f"⚠️ User <code>{user_id}</code> is not authorized. Authorize them first using /a.", parse_mode=enums.ParseMode.HTML)
        return

    new_code = config.generate_secret_code(user_id)
    await message.reply_text(
        f"✅ Secret code generated for user <code>{user_id}</code>!\n\n"
        f"<b>Code:</b> <code>{new_code}</code>\n"
        f"Share this code securely with the user.",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command(["revokesecret"]) & filters.private)
async def revoke_secret_command(client: Client, message: Message):
    """Revoke a secret code (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/revokesecret &lt;secret_code&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return

    code_to_revoke = message.command[1]

    if config.revoke_secret_code(code_to_revoke):
        await message.reply_text(f"✅ Secret code <code>{code_to_revoke}</code> has been revoked.", parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(f"❌ Secret code <code>{code_to_revoke}</code> not found.", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["listauth"]) & filters.private)
async def list_auth_command(client: Client, message: Message):
    """List all authorized users (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    authorized_users = config.authorized_users
    owner_id = config.owner_id
    
    if not authorized_users:
        auth_list = "No authorized users (only owner)"
    else:
        auth_list = "\n".join([f"• <code>{uid}</code>" for uid in authorized_users])
    
    response = f"""
<b>👥 Authorized Users:</b>

<b>Owner:</b> <code>{owner_id}</code>

<b>Authorized Users ({len(authorized_users)}):</b>
{auth_list}
    """
    
    await message.reply_text(response, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["listcodes"]) & filters.private)
async def list_codes_command(client: Client, message: Message):
    """List all user codes (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return

    codes = config.user_secret_codes
    if not codes:
        await message.reply_text("❌ No secret codes generated yet.")
        return

    code_list = "\n".join([f"• User ID: <code>{uid}</code> -> Code: <code>{code}</code>" for code, uid in codes.items()])
    response = f"<b>🔐 User Secret Codes ({len(codes)}):</b>\n\n{code_list}"
    await message.reply_text(response, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["addchat"]) & filters.private)
async def add_chat_command(client: Client, message: Message):
    """Add chat to authorized list (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/addchat &lt;chat_id_or_username&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    
    chat_input = message.command[1]
    chat_id = await resolve_chat_id(chat_input)
    
    if not chat_id:
        await message.reply_text("❌ Invalid chat ID or username!")
        return
    
    if chat_id in config.authorized_chats:
        await message.reply_text("⚠️ Chat is already authorized!")
        return
    
    config.add_authorized_chat(chat_id)
    
    await message.reply_text(f"✅ Chat <code>{chat_id}</code> has been authorized!", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["removechat"]) & filters.private)
async def remove_chat_command(client: Client, message: Message):
    """Remove chat from authorized list (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/removechat &lt;chat_id_or_username&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    
    chat_input = message.command[1]
    chat_id = await resolve_chat_id(chat_input)
    
    if not chat_id:
        await message.reply_text("❌ Invalid chat ID or username!")
        return
    
    if chat_id not in config.authorized_chats:
        await message.reply_text("⚠️ Chat is not in authorized list!")
        return
    
    config.remove_authorized_chat(chat_id)
    
    await message.reply_text(f"✅ Chat <code>{chat_id}</code> has been removed!", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["listchats"]) & filters.private)
async def list_chats_command(client: Client, message: Message):
    """List all authorized chats (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    authorized_chats = config.authorized_chats
    
    if not authorized_chats:
        await message.reply_text("❌ No authorized chats!")
        return
    
    chats_list = ""
    for chat_id in authorized_chats:
        try:
            chat = await client.get_chat(chat_id)
            chat_title = chat.title if chat.title else "Unknown"
            chat_type = "Channel" if chat.type == enums.ChatType.CHANNEL else "Group" if chat.type == enums.ChatType.GROUP or chat.type == enums.ChatType.SUPERGROUP else "Private"
            chats_list += f"• <code>{chat_id}</code> - {chat_title} ({chat_type})\n"
        except Exception:
            chats_list += f"• <code>{chat_id}</code> - Unknown (Cannot fetch info)\n"
    
    response = f"""
<b>💬 Authorized Chats ({len(authorized_chats)}):</b>

{chats_list}
    """
    
    await message.reply_text(response, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["setcmd"]) & filters.private)
async def set_command_command(client: Client, message: Message):
    """Set spam command (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/setcmd &lt;new_command&gt;</code>\nExample: <code>/setcmd spam</code>", parse_mode=enums.ParseMode.HTML)
        return
    
    new_command = message.command[1]
    old_command = config.spam_command
    
    config.spam_command = new_command
    global current_spam_command
    current_spam_command = config.spam_command
    
    await message.reply_text(
        f"✅ Spam command updated!\n\n"
        f"Old: <code>{old_command}</code>\n"
        f"New: <code>{current_spam_command}</code>",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command(["addmsg"]) & filters.private)
async def add_message_command(client: Client, message: Message):
    """Add a new spam message (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text(
            "Usage: <code>/addmsg &lt;message_text&gt;</code>\n\n"
            "Use <code>{{mention}}</code> as placeholder for user mention.\n"
            "Example: <code>/addmsg Hello {{mention}}! Check this out!</code>",
            parse_mode=enums.ParseMode.HTML
        )
        return
    
    new_message = ' '.join(message.command[1:])
    
    if new_message in config.spam_messages:
        await message.reply_text("⚠️ This message already exists in the list!")
        return
    
    config.add_spam_message(new_message)
    
    await message.reply_text(
        f"✅ Spam message added!\n"
        f"Total messages: <code>{len(config.spam_messages)}</code>\n\n"
        f"<b>Message:</b> <code>{new_message}</code>",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command(["delmsg"]) & filters.private)
async def delete_message_command(client: Client, message: Message):
    """Delete a spam message by index (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if len(message.command) < 2:
        messages = config.spam_messages
        if not messages:
            await message.reply_text("❌ No spam messages configured!")
            return
        
        msg_list = ""
        for idx, msg in enumerate(messages, 1):
            msg_list += f"{idx}. `{msg}`\n"
        
        await message.reply_text(
            f"📝 Current spam messages:\n\n{msg_list}\n\n"
            f"Usage: <code>/delmsg &lt;index&gt;</code>\n"
            f"Example: <code>/delmsg 1</code> to delete first message",
            parse_mode=enums.ParseMode.HTML
        )
        return
    
    try:
        index = int(message.command[1]) - 1
        
        if index < 0 or index >= len(config.spam_messages):
            await message.reply_text(f"❌ Invalid index! Please use 1-{len(config.spam_messages)}")
            return
        
        deleted_message = config.spam_messages[index]
        config.remove_spam_message(index)
        
        await message.reply_text(
            f"✅ Message deleted!\n"
            f"Remaining messages: <code>{len(config.spam_messages)}</code>\n\n"
            f"<b>Deleted:</b> <code>{deleted_message}</code>",
            parse_mode=enums.ParseMode.HTML
        )
    except ValueError:
        await message.reply_text("❌ Invalid index! Please provide a number.")

@app.on_message(filters.command(["listmsg"]) & filters.private)
async def list_messages_command(client: Client, message: Message):
    """List all spam messages (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    messages = config.spam_messages
    
    if not messages:
        await message.reply_text("❌ No spam messages configured!")
        return
    
    msg_list = ""
    for idx, msg in enumerate(messages, 1):
        msg_list += f"{idx}. `{msg}`\n"
    
    await message.reply_text(
        f"📝 Spam Messages ({len(messages)}):\n\n{msg_list}",
        parse_mode=enums.ParseMode.HTML
    )

@app.on_message(filters.command(["clrmsg"]) & filters.private)
async def clear_messages_command(client: Client, message: Message):
    """Clear all spam messages (Owner only)"""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔ This command is for owner only!")
        return
    
    if not config.spam_messages:
        await message.reply_text("❌ No spam messages to clear!")
        return
    
    config.spam_messages = ["Hello {mention}! Welcome to the group!"]
    
    await message.reply_text(
        "✅ All spam messages cleared!\n"
        "Default message has been added.",
        parse_mode=enums.ParseMode.HTML
    )

# ========== SECRET CODE AUTH + USER MATCH CHECK + MESSAGE DELETION ==========
@app.on_message(filters.group | filters.channel | filters.private)
async def universal_message_handler(client: Client, message: Message):
    """Universal message handler - SECRET CODE AUTH: Chat + (Code -> User) + (Non-Anon User Match)"""
    
    # Skip if no text
    if not message.text:
        return
    
    # Get the spam command from config
    spam_cmd = current_spam_command.lstrip('/')
    
    # Check if message starts with spam command
    if not message.text.startswith(f"/{spam_cmd}") and not message.text.startswith(spam_cmd):
        return
    
    logger.info(f"Received command: {message.text} in chat {message.chat.id} (type: {message.chat.type})")
    
    # ========== AUTHORIZATION CHECK (Chat + Code -> User) ==========
    # First, check if chat is authorized
    if message.chat.type != enums.ChatType.PRIVATE:
        if not is_chat_authorized(message.chat.id):
            logger.info(f"Chat {message.chat.id} is not authorized")
            # Optionally, delete the command message even if chat is not authorized
            try:
                await client.delete_messages(message.chat.id, message.id)
                logger.info(f"Deleted unauthorized command message {message.id} in unauthorized chat {message.chat.id}")
            except MessageDeleteForbidden:
                 logger.warning(f"Could not delete message {message.id} in {message.chat.id}: Delete Forbidden")
            except Exception as e:
                 logger.error(f"Error deleting message {message.id} in {message.chat.id}: {e}")
            return # Exit if chat is not authorized
    
    # Handle private chat
    if message.chat.type == enums.ChatType.PRIVATE:
        # In PM, just show help
        await message.reply_text(
            f"<b>Spam command detected in PM!</b>\n\n"
            f"To use <code>{current_spam_command}</code>, add me to a group/channel as admin, "
            f"then authorize that chat using <code>/addchat</code> command.\n\n"
            f"Then use: <code>{current_spam_command} &lt;your_secret_code&gt; @username 5</code>",
            parse_mode=enums.ParseMode.HTML
        )
        return

    # ========== PARSE COMMAND FOR SECRET CODE ==========
    parts = message.text.split()
    if len(parts) < 4: # Minimum: /s code target quantity
        logger.info(f"Incomplete command (needs code): {message.text}")
        # Delete the incomplete command message
        try:
            await client.delete_messages(message.chat.id, message.id)
            logger.info(f"Deleted incomplete command message {message.id}")
        except MessageDeleteForbidden:
             logger.warning(f"Could not delete message {message.id}: Delete Forbidden")
        except Exception as e:
             logger.error(f"Error deleting message {message.id}: {e}")
        return

    # Extract parts
    command = parts[0] # /s
    potential_code = parts[1] # The secret code part
    target_input = parts[2] # @target
    quantity_input = parts[3] # quantity

    # ========== AUTHORIZE USING SECRET CODE ==========
    authorized_user_id_from_code = config.get_user_id_from_code(potential_code)
    if not authorized_user_id_from_code:
        logger.info(f"Command contains invalid secret code: {potential_code}")
        # Delete the command message with invalid code
        try:
            await client.delete_messages(message.chat.id, message.id)
            logger.info(f"Deleted command message {message.id} with invalid code in {message.chat.id}")
        except MessageDeleteForbidden:
             logger.warning(f"Could not delete message {message.id}: Delete Forbidden")
        except Exception as e:
             logger.error(f"Error deleting message {message.id}: {e}")
        # Send unauthorized message
        unauth_msg = await message.reply_text("❌ Unauthorized user. Command ignored.")
        # Delete unauthorized message after 20 seconds
        await asyncio.sleep(20)
        try:
            await client.delete_messages(message.chat.id, unauth_msg.id)
            logger.info(f"Deleted unauthorized user message {unauth_msg.id}")
        except MessageDeleteForbidden:
             logger.warning(f"Could not delete unauthorized message {unauth_msg.id}: Delete Forbidden")
        except Exception as e:
             logger.error(f"Error deleting unauthorized message {unauth_msg.id}: {e}")
        return # Exit if code is invalid

    # ========== CHECK IF USER MATCHES (for non-anonymous) ==========
    command_sender_user_id = None
    if message.from_user: # Non-anonymous post
        command_sender_user_id = message.from_user.id
        logger.info(f"Command sent non-anonymously by user ID: {command_sender_user_id}")
        # Check if the user who sent the command matches the user ID linked to the code
        if command_sender_user_id != authorized_user_id_from_code:
            logger.info(f"Command sender ID ({command_sender_user_id}) does not match code's user ID ({authorized_user_id_from_code}).")
            # Delete the command message
            try:
                await client.delete_messages(message.chat.id, message.id)
                logger.info(f"Deleted command message {message.id} from mismatched user {command_sender_user_id}")
            except MessageDeleteForbidden:
                 logger.warning(f"Could not delete message {message.id}: Delete Forbidden")
            except Exception as e:
                 logger.error(f"Error deleting message {message.id}: {e}")
            # Send unauthorized message
            unauth_msg = await message.reply_text("❌ Command sent by a user ID that does not match the secret code's assigned user ID. Command ignored.")
            # Delete unauthorized message after 20 seconds
            await asyncio.sleep(20)
            try:
                await client.delete_messages(message.chat.id, unauth_msg.id)
                logger.info(f"Deleted unauthorized user message {unauth_msg.id}")
            except MessageDeleteForbidden:
                 logger.warning(f"Could not delete unauthorized message {unauth_msg.id}: Delete Forbidden")
            except Exception as e:
                 logger.error(f"Error deleting unauthorized message {unauth_msg.id}: {e}")
            return # Exit if user IDs do not match for non-anonymous post
        else:
            logger.info(f"Command sender ID matches code's user ID. Proceeding with authorization check.")
    else: # Anonymous post or channel post
        logger.info(f"Command sent anonymously or as channel. Using code's user ID ({authorized_user_id_from_code}) for authorization check.")
        # For anonymous posts, we can only rely on the code's linked user ID
        # The check 'is_authorized(authorized_user_id_from_code)' below handles this


    # ========== FINAL AUTHORIZATION: User ID Check (from code) ==========
    # Check if the user ID linked to the code is in the authorized list.
    if not is_authorized(authorized_user_id_from_code):
        logger.info(f"Valid code provided by user ID (or linked to code): {authorized_user_id_from_code}, but this user is not authorized.")
        # Delete the command message
        try:
            await client.delete_messages(message.chat.id, message.id)
            logger.info(f"Deleted command message {message.id} from unauthorized user {authorized_user_id_from_code}")
        except MessageDeleteForbidden:
             logger.warning(f"Could not delete message {message.id}: Delete Forbidden")
        except Exception as e:
             logger.error(f"Error deleting message {message.id}: {e}")
        # Send unauthorized message
        unauth_msg = await message.reply_text("❌ Unauthorized user (code valid, but linked user ID is not authorized). Command ignored.")
        # Delete unauthorized message after 20 seconds
        await asyncio.sleep(20)
        try:
            await client.delete_messages(message.chat.id, unauth_msg.id)
            logger.info(f"Deleted unauthorized user message {unauth_msg.id}")
        except MessageDeleteForbidden:
             logger.warning(f"Could not delete unauthorized message {unauth_msg.id}: Delete Forbidden")
        except Exception as e:
             logger.error(f"Error deleting unauthorized message {unauth_msg.id}: {e}")
        return # Exit if user is not authorized

    # ========== IF AUTHORIZED, DELETE COMMAND MESSAGE ==========
    # The user (either verified sender for non-anon, or linked user for anon) is authorized.
    # Now, delete the command message to hide the code.
    try:
        await client.delete_messages(message.chat.id, message.id)
        logger.info(f"Deleted authorized command message {message.id}")
    except MessageDeleteForbidden:
         logger.warning(f"Could not delete message {message.id}: Delete Forbidden")
    except Exception as e:
         logger.error(f"Error deleting message {message.id}: {e}")

    # ========== VALIDATE QUANTITY ==========
    try:
        quantity = int(quantity_input)
        if quantity < 1 or quantity > 100:
            logger.info(f"Invalid quantity: {quantity}")
            return
    except ValueError:
        logger.info(f"Invalid quantity format: {quantity_input}")
        return
    
    # ========== RESOLVE TARGET USER ==========
    target_id = await resolve_user_id(target_input)
    if not target_id:
        logger.info(f"Could not resolve target: {target_input}")
        return
    
    # ========== GET TARGET USER INFO ==========
    try:
        target_user = await client.get_users(target_id)
        display_name = target_user.first_name or target_user.username or str(target_user.id)
        mention = f'<a href="tg://user?id={target_user.id}">{display_name}</a>'
        logger.info(f"Target user resolved: {target_user.id} ({display_name})")
    except (PeerIdInvalid, UsernameInvalid, UsernameNotOccupied) as e:
        logger.error(f"Error getting target user: {e}")
        return
    
    # ========== BOT ADMIN CHECK ==========
    try:
        chat_member = await client.get_chat_member(message.chat.id, "me")
        if chat_member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            logger.info(f"Bot is not admin in chat {message.chat.id}, status: {chat_member.status}")
            return
        logger.info(f"Bot admin status confirmed in chat {message.chat.id}")
    except ChatAdminRequired:
        logger.info(f"Bot is not admin in chat {message.chat.id} (ChatAdminRequired)")
        return
    except Exception as e:
        logger.error(f"Error checking admin status in chat {message.chat.id}: {e}")
        return
    
    # ========== SEND SPAM MESSAGES ==========
    messages = config.spam_messages
    if not messages:
        logger.info("No spam messages configured")
        return
    
    logger.info(f"Starting to send {quantity} messages to {display_name} in chat {message.chat.id}")
    
    message_pool = []
    for i in range(quantity):
        if i % len(messages) == 0:
            shuffled = random.sample(messages, len(messages))
            message_pool.extend(shuffled)
    
    message_pool = message_pool[:quantity]
    
    success_count = 0
    for msg_text in message_pool:
        try:
            formatted_msg = msg_text.format(mention=mention)
            
            await client.send_message(
                chat_id=message.chat.id,
                text=formatted_msg,
                parse_mode=enums.ParseMode.HTML
            )
            
            success_count += 1
            await asyncio.sleep(random.uniform(0.1, 0.5)) # Faster sending now that command is deleted
            
        except FloodWait as e:
            logger.warning(f"Flood wait: {e.value} seconds")
            await asyncio.sleep(e.value)
            continue
        except ChatWriteForbidden:
            logger.error("Bot doesn't have permission to send messages")
            break
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            continue
    
    logger.info(f"✅ Successfully sent {success_count}/{quantity} messages to {display_name} in chat {message.chat.id}")

# Block owner commands in groups/channels
owner_commands = ["a", "add", "r", "remove", "gensecret", "revokesecret", "listauth", "listcodes", "setcmd",
                  "addmsg", "delmsg", "listmsg", "clrmsg",
                  "addchat", "removechat", "listchats"]

@app.on_message(filters.command(owner_commands) & (filters.group | filters.channel))
async def block_owner_commands_in_chats(client: Client, message: Message):
    """Block owner commands in groups/channels - SILENT"""
    # Optionally, delete the command message if sent in a group/channel
    try:
        await client.delete_messages(message.chat.id, message.id)
        logger.info(f"Deleted owner command {message.text} in non-PM chat {message.chat.id}")
    except MessageDeleteForbidden:
         logger.warning(f"Could not delete owner command message {message.id}: Delete Forbidden")
    except Exception as e:
         logger.error(f"Error deleting owner command message {message.id}: {e}")
    return # Do nothing else

def main():
    """Start the bot"""
    global current_spam_command
    current_spam_command = config.spam_command
    
    print("=" * 70)
    print("🤖 TELEGRAM SPAM BOT - SECRET CODE + USER MATCH + DELETE")
    print("=" * 70)
    print(f"👑 Owner ID: {config.owner_id}")
    print(f"👥 Authorized users: {len(config.authorized_users)}")
    print(f"💬 Authorized chats: {len(config.authorized_chats)}")
    print(f"🔐 Secret Codes: {len(config.user_secret_codes)}")
    print(f"🔧 Spam command: {current_spam_command}")
    print(f"📝 Spam messages: {len(config.spam_messages)}")
    print("=" * 70)
    print("✅ AUTHORIZATION RULES:")
    print("• Chat MUST be authorized.")
    print("• User MUST be authorized (via unique secret code).")
    print("• For NON-ANONYMOUS posts: Command sender ID MUST match code's user ID.")
    print("• For ANONYMOUS posts: Code's user ID MUST be authorized.")
    print("• Command: /s <your_unique_code> <target> <quantity>")
    print("=" * 70)
    print("🚀 HOW TO SETUP:")
    print("1. Make bot ADMIN in chat")
    print("2. In PM: /addchat <chat_id>")
    print("3. In PM: /a <user_id> (authorize user)")
    print("4. In PM: /gensecret <user_id> (generate unique code for user)")
    print("5. Share code securely with user")
    print("6. In authorized chat: /s <code> @username 5 (user sends)")
    print("   - Non-anonymous: Sender ID must match code's user ID.")
    print("   - Anonymous: Code's user ID must be authorized.")
    print("=" * 70)
    print("🤖 Bot is starting...")
    print("=" * 70)
    
    app.run()

if __name__ == "__main__":
    # Validate required environment variables
    if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
        print("❌ ERROR: Missing environment variables!")
        print("Please create a .env file with format:")
        print("API_ID=22207xx, API_HASH=hash, BOT_TOKEN=token, OWNER_ID=694924xxx")
        print("\nOr set environment variables manually.")
        exit(1)
    
    main()