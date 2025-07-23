"""
Text processing utilities for Echo bot.
"""

import re
from typing import List, Optional
from urllib.parse import urlparse


def clean_discord_content(content: str) -> str:
    """
    Clean Discord message content for AI training.
    
    :param content: Raw Discord message content
    :return: Cleaned content
    """
    if not content:
        return ""
    
    # Remove Discord mentions
    content = re.sub(r'<@!?(\d+)>', '[USER]', content)
    content = re.sub(r'<@&(\d+)>', '[ROLE]', content)
    content = re.sub(r'<#(\d+)>', '[CHANNEL]', content)
    
    # Remove Discord emojis
    content = re.sub(r'<a?:\w+:\d+>', '[EMOJI]', content)
    
    # Clean URLs but keep some context
    content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '[URL]', content)
    
    # Remove multiple whitespaces and normalize
    content = re.sub(r'\s+', ' ', content)
    content = content.strip()
    
    return content


def is_valid_message_content(content: str) -> bool:
    """
    Check if message content is valid for training.
    
    :param content: Message content to validate
    :return: True if valid, False otherwise
    """
    if not content or len(content.strip()) == 0:
        return False
    
    # Skip very short messages
    if len(content.strip()) < 3:
        return False
    
    # Skip messages that are mostly special characters
    if len(re.sub(r'[^\w\s]', '', content)) < len(content) * 0.3:
        return False
    
    # Skip bot commands (starting with common prefixes)
    if content.strip().startswith(('!', '/', '.', '?', '$', '+', '-', '>', '<')):
        return False
    
    return True


def extract_conversation_context(messages: List[dict], target_message_id: str, context_size: int = 5) -> List[dict]:
    """
    Extract conversation context around a target message.
    
    :param messages: List of message dictionaries
    :param target_message_id: ID of the target message
    :param context_size: Number of messages to include before and after
    :return: List of context messages
    """
    try:
        target_index = next(i for i, msg in enumerate(messages) if msg.get('message_id') == target_message_id)
    except StopIteration:
        return []
    
    start_index = max(0, target_index - context_size)
    end_index = min(len(messages), target_index + context_size + 1)
    
    return messages[start_index:end_index]


def tokenize_for_training(content: str) -> List[str]:
    """
    Simple tokenization for training data preparation.
    
    :param content: Text content to tokenize
    :return: List of tokens
    """
    # Basic word tokenization
    tokens = re.findall(r'\b\w+\b|[^\w\s]', content.lower())
    return [token for token in tokens if token.strip()]


def estimate_reading_time(content: str, words_per_minute: int = 200) -> float:
    """
    Estimate reading time for content.
    
    :param content: Text content
    :param words_per_minute: Reading speed in words per minute
    :return: Estimated reading time in seconds
    """
    word_count = len(content.split())
    return (word_count / words_per_minute) * 60


def truncate_content(content: str, max_length: int = 2000) -> str:
    """
    Truncate content to fit Discord message limits.
    
    :param content: Content to truncate
    :param max_length: Maximum length allowed
    :return: Truncated content
    """
    if len(content) <= max_length:
        return content
    
    # Try to truncate at sentence boundary
    truncated = content[:max_length]
    last_sentence = truncated.rfind('. ')
    
    if last_sentence > max_length * 0.7:  # If we can keep at least 70% of content
        return truncated[:last_sentence + 1]
    else:
        return truncated[:max_length - 3] + "..."


def extract_mentions(content: str) -> dict:
    """
    Extract Discord mentions from message content.
    
    :param content: Message content
    :return: Dictionary with extracted mentions
    """
    users = re.findall(r'<@!?(\d+)>', content)
    roles = re.findall(r'<@&(\d+)>', content)
    channels = re.findall(r'<#(\d+)>', content)
    
    return {
        'users': users,
        'roles': roles,
        'channels': channels
    }


def contains_url(content: str) -> bool:
    """
    Check if content contains URLs.
    
    :param content: Content to check
    :return: True if contains URLs, False otherwise
    """
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.search(url_pattern, content))


def normalize_whitespace(content: str) -> str:
    """
    Normalize whitespace in content.
    
    :param content: Content to normalize
    :return: Normalized content
    """
    # Replace multiple whitespaces with single space
    content = re.sub(r'\s+', ' ', content)
    # Remove leading/trailing whitespace
    return content.strip()