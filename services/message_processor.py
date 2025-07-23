""""
Message processing service for Echo bot.

Handles collection, analysis, and preprocessing of user messages for AI training.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, AsyncGenerator
import aiosqlite
import discord
from discord.ext import commands

from utils.text_processor import (
    clean_discord_content, 
    is_valid_message_content,
    extract_conversation_context,
    tokenize_for_training
)
from utils.validation import (
    validate_discord_id,
    validate_message_content_for_training,
    validate_channel_permissions,
    validate_training_dataset_size
)


class MessageProcessor:
    """
    Service for processing and analyzing user messages.
    
    This service handles:
    - Message collection from Discord channels
    - Data preprocessing for AI training
    - Analysis status tracking
    - Dataset preparation for model fine-tuning
    """
    
    def __init__(self, bot: commands.Bot, db_path: str):
        self.bot = bot
        self.db_path = db_path
        self._analysis_tasks = {}  # Track running analysis tasks
    
    async def is_analysis_in_progress(self, user_id: int, server_id: int) -> bool:
        """
        Check if analysis is currently in progress for a user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: True if analysis is in progress, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT training_status FROM echo_profiles WHERE user_id = ? AND server_id = ?",
                (str(user_id), str(server_id))
            )
            result = await cursor.fetchone()
            
            if result:
                return result[0] == 'in_progress'
            
            return False
    
    async def start_analysis(
        self, 
        user_id: int, 
        server_id: int, 
        cutoff_date: datetime,
        requester_id: int
    ) -> None:
        """
        Start message analysis for a user.
        
        :param user_id: Discord user ID to analyze
        :param server_id: Discord server ID
        :param cutoff_date: Only analyze messages before this date
        :param requester_id: ID of user who requested the analysis
        """
        # Create or update profile record
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO echo_profiles 
                (user_id, server_id, cutoff_date, training_status, requester_id, started_at, last_updated)
                VALUES (?, ?, ?, 'in_progress', ?, ?, ?)
            """, (
                str(user_id), str(server_id), cutoff_date.date(),
                str(requester_id), datetime.now(), datetime.now()
            ))
            await db.commit()
        
        # Start background analysis task
        task_key = f"{user_id}_{server_id}"
        if task_key in self._analysis_tasks:
            self._analysis_tasks[task_key].cancel()
        
        self._analysis_tasks[task_key] = asyncio.create_task(
            self._run_analysis(user_id, server_id, cutoff_date, requester_id)
        )
    
    async def _run_analysis(
        self, 
        user_id: int, 
        server_id: int, 
        cutoff_date: datetime,
        requester_id: int
    ) -> None:
        """
        Run the complete analysis process in background.
        """
        try:
            # Step 1: Collect messages
            await self._update_analysis_progress(user_id, server_id, 10, "Collecting messages...")
            messages = await self.collect_user_messages(user_id, server_id, cutoff_date)
            
            if not messages:
                raise Exception("No messages found for this user before the cutoff date")
            
            # Validate dataset size
            is_valid, error_msg = validate_training_dataset_size(len(messages))
            if not is_valid:
                raise Exception(error_msg)
            
            # Step 2: Store messages in database
            await self._update_analysis_progress(user_id, server_id, 30, "Storing messages...")
            await self._store_messages(messages, user_id, server_id)
            
            # Step 3: Preprocess messages
            await self._update_analysis_progress(user_id, server_id, 60, "Preprocessing messages...")
            processed_messages = await self.preprocess_messages(messages)
            
            # Step 4: Prepare training dataset
            await self._update_analysis_progress(user_id, server_id, 80, "Preparing training dataset...")
            dataset_path = await self.prepare_training_dataset(user_id, server_id)
            
            # Step 5: Mark as completed
            await self._update_analysis_progress(user_id, server_id, 100, "Analysis completed")
            await self._mark_analysis_complete(user_id, server_id, dataset_path, len(messages))
            
        except Exception as e:
            await self._mark_analysis_failed(user_id, server_id, str(e))
        finally:
            # Clean up task reference
            task_key = f"{user_id}_{server_id}"
            if task_key in self._analysis_tasks:
                del self._analysis_tasks[task_key]
    
    async def _update_analysis_progress(
        self, 
        user_id: int, 
        server_id: int, 
        progress: int, 
        status_message: str = None
    ) -> None:
        """Update analysis progress in database."""
        async with aiosqlite.connect(self.db_path) as db:
            update_data = [progress, datetime.now(), str(user_id), str(server_id)]
            query = "UPDATE echo_profiles SET training_progress = ?, last_updated = ?"
            
            if status_message:
                query += ", error_message = ?"
                update_data.insert(-2, status_message)
            
            query += " WHERE user_id = ? AND server_id = ?"
            
            await db.execute(query, update_data)
            await db.commit()
    
    async def _mark_analysis_complete(
        self, 
        user_id: int, 
        server_id: int, 
        dataset_path: str,
        message_count: int
    ) -> None:
        """Mark analysis as completed and trigger model training."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE echo_profiles 
                SET training_status = 'analysis_completed', training_progress = 100, 
                    completed_at = ?, model_path = ?, total_messages = ?, 
                    processed_messages = ?, last_updated = ?, error_message = NULL
                WHERE user_id = ? AND server_id = ?
            """, (
                datetime.now(), dataset_path, message_count, message_count,
                datetime.now(), str(user_id), str(server_id)
            ))
            await db.commit()
        
        # Trigger model training if we have a personality engine callback
        if hasattr(self, '_personality_engine_callback'):
            try:
                await self._personality_engine_callback(user_id, server_id, dataset_path)
            except Exception as e:
                await self._mark_analysis_failed(user_id, server_id, f"Model training failed: {str(e)}")
    
    def set_personality_engine_callback(self, callback):
        """Set callback to trigger personality engine after analysis."""
        self._personality_engine_callback = callback
    
    async def _mark_analysis_failed(self, user_id: int, server_id: int, error_message: str) -> None:
        """Mark analysis as failed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE echo_profiles 
                SET training_status = 'failed', error_message = ?, last_updated = ?
                WHERE user_id = ? AND server_id = ?
            """, (error_message, datetime.now(), str(user_id), str(server_id)))
            await db.commit()
    
    async def get_analysis_status(self, user_id: int, server_id: int) -> Dict:
        """
        Get the current status of analysis for a user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: Dictionary containing analysis status information
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT training_status, training_progress, total_messages, 
                       processed_messages, started_at, completed_at, error_message
                FROM echo_profiles 
                WHERE user_id = ? AND server_id = ?
            """, (str(user_id), str(server_id)))
            result = await cursor.fetchone()
            
            if not result:
                return {
                    "status": "not_started",
                    "progress": 0,
                    "total_messages": 0,
                    "processed_messages": 0,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None
                }
            
            return {
                "status": result[0],
                "progress": result[1] or 0,
                "total_messages": result[2] or 0,
                "processed_messages": result[3] or 0,
                "started_at": result[4],
                "completed_at": result[5],
                "error_message": result[6]
            }
    
    async def collect_user_messages(
        self, 
        user_id: int, 
        server_id: int, 
        cutoff_date: datetime
    ) -> List[Dict]:
        """
        Collect messages from a user before the cutoff date.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param cutoff_date: Only collect messages before this date
        :return: List of message dictionaries
        """
        guild = self.bot.get_guild(server_id)
        if not guild:
            raise Exception(f"Guild {server_id} not found or bot not in guild")
        
        user = guild.get_member(user_id)
        if not user:
            raise Exception(f"User {user_id} not found in guild")
        
        messages = []
        bot_member = guild.get_member(self.bot.user.id)
        
        for channel in guild.text_channels:
            try:
                # Check bot permissions
                is_valid, error_msg = validate_channel_permissions(channel, bot_member)
                if not is_valid:
                    continue  # Skip channels where bot lacks permissions
                
                # Collect messages from this channel
                async for message in self._get_user_messages_from_channel(
                    channel, user_id, cutoff_date
                ):
                    messages.append(message)
                    
                    # Respect rate limits and prevent excessive memory usage
                    if len(messages) >= 10000:  # Configurable limit
                        break
                        
            except discord.Forbidden:
                continue  # Skip channels we can't access
            except Exception as e:
                print(f"Error collecting from channel {channel.name}: {e}")
                continue
        
        return messages
    
    async def _get_user_messages_from_channel(
        self, 
        channel: discord.TextChannel, 
        user_id: int, 
        cutoff_date: datetime
    ) -> AsyncGenerator[Dict, None]:
        """Get messages from a specific user in a channel."""
        try:
            async for message in channel.history(
                limit=None,
                before=cutoff_date,
                oldest_first=False
            ):
                if message.author.id == user_id and not message.author.bot:
                    if message.content and is_valid_message_content(message.content):
                        yield {
                            'message_id': str(message.id),
                            'user_id': str(message.author.id),
                            'server_id': str(message.guild.id),
                            'channel_id': str(message.channel.id),
                            'message_content': message.content,
                            'timestamp': message.created_at,
                            'is_processed': False
                        }
                        
        except discord.Forbidden:
            pass  # No access to this channel
        except Exception as e:
            print(f"Error getting messages from {channel.name}: {e}")
    
    async def _store_messages(self, messages: List[Dict], user_id: int, server_id: int) -> None:
        """Store collected messages in database."""
        async with aiosqlite.connect(self.db_path) as db:
            # Clear existing messages for this user/server
            await db.execute(
                "DELETE FROM user_messages WHERE user_id = ? AND server_id = ?",
                (str(user_id), str(server_id))
            )
            
            # Insert new messages
            for message in messages:
                await db.execute("""
                    INSERT INTO user_messages 
                    (user_id, server_id, channel_id, message_content, timestamp, message_id, is_processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    message['user_id'], message['server_id'], message['channel_id'],
                    message['message_content'], message['timestamp'], message['message_id'],
                    message['is_processed']
                ))
            
            await db.commit()
    
    async def preprocess_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Preprocess collected messages for AI training.
        
        :param messages: List of raw message dictionaries
        :return: List of preprocessed message dictionaries
        """
        processed_messages = []
        
        for message in messages:
            content = message['message_content']
            
            # Clean the content
            cleaned_content = clean_discord_content(content)
            
            # Validate cleaned content
            is_valid, _ = validate_message_content_for_training(cleaned_content)
            if not is_valid:
                continue
            
            # Create processed message
            processed_message = message.copy()
            processed_message['message_content'] = cleaned_content
            processed_message['word_count'] = len(cleaned_content.split())
            processed_message['char_count'] = len(cleaned_content)
            processed_message['is_processed'] = True
            
            processed_messages.append(processed_message)
        
        return processed_messages
    
    async def prepare_training_dataset(self, user_id: int, server_id: int) -> str:
        """
        Prepare training dataset for AI model fine-tuning.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: Path to prepared dataset file
        """
        # Get processed messages from database
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT message_content, timestamp, channel_id
                FROM user_messages 
                WHERE user_id = ? AND server_id = ? AND is_processed = 1
                ORDER BY timestamp ASC
            """, (str(user_id), str(server_id)))
            messages = await cursor.fetchall()
        
        if not messages:
            raise Exception("No processed messages found")
        
        # Prepare dataset in format suitable for Ollama training
        dataset = []
        for i, (content, timestamp, channel_id) in enumerate(messages):
            # Create training examples in conversation format
            dataset.append({
                "prompt": f"You are responding in a Discord conversation. Context: Message {i+1}",
                "response": content,
                "metadata": {
                    "timestamp": timestamp,
                    "channel_id": channel_id,
                    "message_index": i
                }
            })
        
        # Create dataset directory if it doesn't exist
        dataset_dir = os.path.join(os.getcwd(), "datasets")
        os.makedirs(dataset_dir, exist_ok=True)
        
        # Save dataset to file
        dataset_filename = f"user_{user_id}_server_{server_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        dataset_path = os.path.join(dataset_dir, dataset_filename)
        
        with open(dataset_path, 'w', encoding='utf-8') as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False, default=str)
        
        return dataset_path
    
    async def cleanup_old_data(self, days_old: int = 30) -> int:
        """
        Clean up old message data and analysis records.
        
        :param days_old: Remove data older than this many days
        :return: Number of records cleaned up
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        cleaned_count = 0
        
        async with aiosqlite.connect(self.db_path) as db:
            # Clean up old echo profiles
            cursor = await db.execute(
                "DELETE FROM echo_profiles WHERE created_at < ?",
                (cutoff_date,)
            )
            cleaned_count += cursor.rowcount
            
            # Clean up old user messages
            cursor = await db.execute(
                "DELETE FROM user_messages WHERE created_at < ?",
                (cutoff_date,)
            )
            cleaned_count += cursor.rowcount
            
            await db.commit()
        
        # Clean up old dataset files
        dataset_dir = os.path.join(os.getcwd(), "datasets")
        if os.path.exists(dataset_dir):
            for filename in os.listdir(dataset_dir):
                file_path = os.path.join(dataset_dir, filename)
                if os.path.isfile(file_path):
                    file_age = datetime.now() - datetime.fromtimestamp(os.path.getctime(file_path))
                    if file_age.days > days_old:
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except OSError:
                            pass
        
        return cleaned_count