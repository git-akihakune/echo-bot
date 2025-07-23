"""
Validation utilities for Echo bot.
"""

import re
from datetime import datetime
from typing import Optional
import discord


def validate_discord_id(discord_id: str) -> bool:
    """
    Validate Discord ID format.
    
    :param discord_id: Discord ID to validate
    :return: True if valid, False otherwise
    """
    if not discord_id or not isinstance(discord_id, str):
        return False
    
    # Discord IDs are 17-20 digit snowflakes
    return re.match(r'^\d{17,20}$', discord_id) is not None


def validate_user_permissions(user: discord.Member, target_user: discord.Member) -> bool:
    """
    Validate if user has permission to analyze target user.
    
    :param user: User requesting analysis
    :param target_user: Target user to analyze
    :return: True if allowed, False otherwise
    """
    # Allow self-analysis
    if user.id == target_user.id:
        return True
    
    # Allow server administrators
    if user.guild_permissions.administrator:
        return True
    
    # Allow users with manage_messages permission
    if user.guild_permissions.manage_messages:
        return True
    
    return False


def validate_cutoff_date(date_str: str) -> tuple[bool, Optional[str]]:
    """
    Validate cutoff date format and value.
    
    :param date_str: Date string to validate
    :return: Tuple of (is_valid, error_message)
    """
    if not date_str:
        return False, "Date cannot be empty"
    
    # Check format
    if not re.match(r'^\d{1,2}\.\d{1,2}\.\d{4}$', date_str):
        return False, "Date must be in DD.MM.YYYY format"
    
    try:
        parsed_date = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return False, "Invalid date values"
    
    # Check if date is not in the future
    if parsed_date > datetime.now():
        return False, "Cutoff date cannot be in the future"
    
    # Check if date is not too far in the past (optional limit)
    min_date = datetime(2015, 1, 1)  # Discord's launch year
    if parsed_date < min_date:
        return False, "Cutoff date cannot be before 2015"
    
    return True, None


def validate_session_limits(server_id: str, current_sessions: int, max_sessions: int) -> tuple[bool, Optional[str]]:
    """
    Validate session limits for a server.
    
    :param server_id: Server ID
    :param current_sessions: Current number of active sessions
    :param max_sessions: Maximum allowed sessions
    :return: Tuple of (is_valid, error_message)
    """
    if current_sessions >= max_sessions:
        return False, f"Maximum number of active sessions ({max_sessions}) reached for this server"
    
    return True, None


def validate_message_content_for_training(content: str) -> tuple[bool, Optional[str]]:
    """
    Validate message content for AI training.
    
    :param content: Message content to validate
    :return: Tuple of (is_valid, error_message)
    """
    if not content or len(content.strip()) == 0:
        return False, "Empty message content"
    
    # Check minimum length
    if len(content.strip()) < 3:
        return False, "Message too short for training"
    
    # Check maximum length
    if len(content) > 2000:
        return False, "Message too long"
    
    # Check if mostly special characters
    alphanumeric_count = len(re.sub(r'[^\w\s]', '', content))
    if alphanumeric_count < len(content) * 0.3:
        return False, "Message contains too many special characters"
    
    return True, None


def validate_model_name(model_name: str) -> tuple[bool, Optional[str]]:
    """
    Validate AI model name.
    
    :param model_name: Model name to validate
    :return: Tuple of (is_valid, error_message)
    """
    if not model_name:
        return False, "Model name cannot be empty"
    
    # Basic validation for model name format
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$', model_name):
        return False, "Invalid model name format"
    
    if len(model_name) > 100:
        return False, "Model name too long"
    
    return True, None


def validate_channel_permissions(channel: discord.TextChannel, bot_user: discord.Member) -> tuple[bool, Optional[str]]:
    """
    Validate bot permissions in a channel.
    
    :param channel: Channel to validate
    :param bot_user: Bot user member
    :return: Tuple of (is_valid, error_message)
    """
    permissions = channel.permissions_for(bot_user)
    
    required_permissions = [
        ('read_messages', 'Read Messages'),
        ('send_messages', 'Send Messages'),
        ('read_message_history', 'Read Message History'),
        ('embed_links', 'Embed Links')
    ]
    
    missing_permissions = []
    for perm_name, perm_display in required_permissions:
        if not getattr(permissions, perm_name):
            missing_permissions.append(perm_display)
    
    if missing_permissions:
        return False, f"Missing permissions: {', '.join(missing_permissions)}"
    
    return True, None


def validate_training_dataset_size(message_count: int, min_messages: int = 50, max_messages: int = 10000) -> tuple[bool, Optional[str]]:
    """
    Validate training dataset size.
    
    :param message_count: Number of messages in dataset
    :param min_messages: Minimum required messages
    :param max_messages: Maximum allowed messages
    :return: Tuple of (is_valid, error_message)
    """
    if message_count < min_messages:
        return False, f"Insufficient messages for training. Found {message_count}, need at least {min_messages}"
    
    if message_count > max_messages:
        return False, f"Too many messages for training. Found {message_count}, maximum is {max_messages}"
    
    return True, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file system use.
    
    :param filename: Original filename
    :return: Sanitized filename
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip('. ')
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = "untitled"
    
    # Limit length
    if len(sanitized) > 255:
        sanitized = sanitized[:255]
    
    return sanitized