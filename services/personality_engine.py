""""
Personality engine service for Echo bot.

Handles AI model training, personality profile creation, and response generation.
"""

import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiosqlite

from services.ollama_client import OllamaClient
from utils.text_processor import (
    truncate_content,
    estimate_reading_time,
    normalize_whitespace
)
from utils.validation import validate_discord_id


class PersonalityEngine:
    """
    Service for managing AI personality profiles and response generation.
    
    This service handles:
    - AI model fine-tuning with user data
    - Personality profile creation and management
    - Context-aware response generation
    - Conversation timing and pacing
    """
    
    def __init__(self, db_path: str, config: Dict):
        self.db_path = db_path
        self.config = config.get('echo', {})
        
        # Initialize Ollama client
        self.ollama = OllamaClient(
            host=self.config.get('ollama_host', 'http://localhost:11434'),
            base_model=self.config.get('base_model', 'dolphin3:latest')
        )
        
        # Response generation settings
        self.max_response_length = self.config.get('max_response_length', 2000)
        self.response_delay_min = self.config.get('response_delay_min', 1.0)
        self.response_delay_max = self.config.get('response_delay_max', 5.0)
        self.conversation_initiation_chance = self.config.get('conversation_initiation_chance', 0.1)
    
    async def create_personality_profile(
        self, 
        user_id: int, 
        server_id: int, 
        dataset_path: str
    ) -> Dict:
        """
        Create a personality profile by fine-tuning an AI model.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param dataset_path: Path to prepared training dataset
        :return: Dictionary containing profile information
        """
        try:
            # Check Ollama availability
            is_available, error_msg = await self.ollama.check_ollama_availability()
            if not is_available:
                raise Exception(f"Ollama service not available: {error_msg}")
            
            # Ensure base model is available
            base_available = await self.ollama.ensure_base_model_available()
            if not base_available:
                raise Exception("Base model not available for fine-tuning")
            
            # Update database status to training
            await self._update_training_status(
                user_id, server_id, 'training', 0, "Starting model training..."
            )
            
            # Create fine-tuned model
            training_config = {
                "epochs": self.config.get('training_epochs', 10),
                "batch_size": self.config.get('batch_size', 4)
            }
            
            success, model_name, error_message = await self.ollama.create_fine_tuned_model(
                user_id, server_id, dataset_path, training_config
            )
            
            if not success:
                await self._update_training_status(
                    user_id, server_id, 'failed', 0, error_message
                )
                raise Exception(error_message)
            
            # Test the model
            await self._update_training_status(
                user_id, server_id, 'training', 90, "Testing model..."
            )
            
            test_successful = await self._test_model(model_name)
            if not test_successful:
                await self._update_training_status(
                    user_id, server_id, 'failed', 90, "Model validation failed"
                )
                raise Exception("Model validation failed")
            
            # Mark as completed
            await self._update_training_status(
                user_id, server_id, 'completed', 100, None, model_name
            )
            
            return {
                "user_id": user_id,
                "server_id": server_id,
                "model_name": model_name,
                "training_status": "completed",
                "created_at": datetime.now(),
                "last_updated": datetime.now()
            }
            
        except Exception as e:
            await self._update_training_status(
                user_id, server_id, 'failed', 0, str(e)
            )
            raise e
    
    async def _update_training_status(
        self, 
        user_id: int, 
        server_id: int, 
        status: str, 
        progress: int,
        error_message: str = None,
        model_name: str = None
    ) -> None:
        """Update training status in database."""
        async with aiosqlite.connect(self.db_path) as db:
            update_fields = [
                "training_status = ?",
                "training_progress = ?",
                "last_updated = ?"
            ]
            update_values = [status, progress, datetime.now()]
            
            if error_message is not None:
                update_fields.append("error_message = ?")
                update_values.append(error_message)
            
            if model_name:
                update_fields.append("model_path = ?")
                update_values.append(model_name)
            
            if status == 'completed':
                update_fields.append("completed_at = ?")
                update_values.append(datetime.now())
            
            # Add WHERE clause parameters
            update_values.extend([str(user_id), str(server_id)])
            
            query = f"""
                UPDATE echo_profiles 
                SET {', '.join(update_fields)}
                WHERE user_id = ? AND server_id = ?
            """
            
            await db.execute(query, update_values)
            await db.commit()
    
    async def _test_model(self, model_name: str) -> bool:
        """Test the fine-tuned model."""
        try:
            test_prompts = [
                "Hello, how are you?",
                "What do you think about this?",
                "How was your day?"
            ]
            
            for prompt in test_prompts:
                response = await self.ollama.generate_response(
                    model_name, prompt, max_tokens=50, temperature=0.7
                )
                
                if not response:
                    return False
                
                # Basic validation
                if not self.validate_model_response(response):
                    return False
            
            return True
            
        except Exception as e:
            print(f"Error testing model {model_name}: {e}")
            return False
    
    async def get_personality_profile(self, user_id: int, server_id: int) -> Optional[Dict]:
        """
        Retrieve personality profile for a user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: Profile dictionary or None if not found
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, user_id, server_id, model_path, training_status, 
                       created_at, last_updated, total_messages
                FROM echo_profiles 
                WHERE user_id = ? AND server_id = ? AND training_status = 'completed'
            """, (str(user_id), str(server_id)))
            
            result = await cursor.fetchone()
            if not result:
                return None
            
            return {
                "profile_id": result[0],
                "user_id": result[1],
                "server_id": result[2],
                "model_name": result[3],
                "training_status": result[4],
                "created_at": result[5],
                "last_updated": result[6],
                "total_messages": result[7]
            }
    
    async def generate_response(
        self, 
        user_id: int, 
        server_id: int, 
        context: List[Dict],
        channel_history: List[Dict] = None
    ) -> Optional[str]:
        """
        Generate a response using the user's personality profile.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param context: Recent conversation context
        :param channel_history: Channel message history
        :return: Generated response or None if unable to generate
        """
        try:
            # Get personality profile
            profile = await self.get_personality_profile(user_id, server_id)
            if not profile:
                return None
            
            model_name = profile['model_name']
            
            # Prepare context prompt
            context_prompt = self._prepare_context_prompt(context, channel_history)
            
            # Generate response
            response = await self.ollama.generate_response(
                model_name=model_name,
                prompt=context_prompt,
                context=context,
                max_tokens=200,
                temperature=0.8
            )
            
            if not response:
                return None
            
            # Post-process response
            response = self._post_process_response(response)
            
            # Validate response
            if not self.validate_model_response(response):
                return None
            
            return response
            
        except Exception as e:
            print(f"Error generating response for user {user_id}: {e}")
            return None
    
    def _prepare_context_prompt(
        self, 
        context: List[Dict], 
        channel_history: List[Dict] = None
    ) -> str:
        """Prepare context prompt for the model."""
        prompt_parts = []
        
        # Add recent channel context
        if channel_history:
            recent_messages = channel_history[-3:]  # Last 3 messages
            for msg in recent_messages:
                author = msg.get('author', 'Unknown')
                content = msg.get('content', '')
                prompt_parts.append(f"{author}: {content}")
        
        # Add conversation context
        if context:
            for msg in context[-2:]:  # Last 2 context messages
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    prompt_parts.append(f"User: {content}")
                else:
                    prompt_parts.append(f"Assistant: {content}")
        
        # Default prompt if no context
        if not prompt_parts:
            prompt_parts.append("Continue the conversation naturally.")
        
        return "\n".join(prompt_parts)
    
    def _post_process_response(self, response: str) -> str:
        """Post-process generated response."""
        # Normalize whitespace
        response = normalize_whitespace(response)
        
        # Remove common AI prefixes
        prefixes_to_remove = [
            "Assistant: ",
            "AI: ",
            "Bot: ",
            "Echo: ",
            "Response: "
        ]
        
        for prefix in prefixes_to_remove:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()
        
        # Truncate if too long
        response = truncate_content(response, self.max_response_length)
        
        # Ensure response ends properly
        if response and not response[-1] in '.!?':
            # Don't add punctuation to incomplete sentences
            pass
        
        return response
    
    async def should_respond(
        self, 
        user_id: int, 
        server_id: int, 
        channel_history: List[Dict]
    ) -> bool:
        """
        Determine if the echo should respond based on conversation context.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param channel_history: Recent channel message history
        :return: True if should respond, False otherwise
        """
        try:
            if not channel_history:
                return False
            
            last_message = channel_history[-1]
            
            # Don't respond to own messages or bot messages
            if last_message.get('author_id') == str(user_id):
                return False
            
            if last_message.get('is_bot', False):
                return False
            
            # Check if mentioned
            mentions = last_message.get('mentions', [])
            if str(user_id) in mentions:
                return True
            
            # Check time since last message
            last_message_time = last_message.get('timestamp')
            if last_message_time:
                try:
                    if isinstance(last_message_time, str):
                        last_time = datetime.fromisoformat(last_message_time.replace('Z', '+00:00'))
                    else:
                        last_time = last_message_time
                    
                    time_diff = (datetime.now() - last_time).total_seconds()
                    
                    # Don't respond immediately
                    if time_diff < 10:
                        return False
                    
                    # Higher chance to respond to recent messages
                    if time_diff < 300:  # 5 minutes
                        return random.random() < 0.3
                    
                except (ValueError, TypeError):
                    pass
            
            # Random chance to respond based on conversation activity
            activity_score = min(len(channel_history), 10) / 10.0
            base_chance = 0.1 * activity_score
            
            return random.random() < base_chance
            
        except Exception as e:
            print(f"Error determining if should respond: {e}")
            return False
    
    async def get_response_timing(self, user_id: int, server_id: int) -> float:
        """
        Calculate natural response timing for the user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: Delay in seconds before responding
        """
        # Base delay with some randomness
        base_delay = random.uniform(self.response_delay_min, self.response_delay_max)
        
        # Add typing simulation delay
        typing_delay = random.uniform(1.0, 3.0)
        
        return base_delay + typing_delay
    
    async def initiate_conversation(
        self, 
        user_id: int, 
        server_id: int, 
        channel_id: int
    ) -> Optional[str]:
        """
        Generate a conversation starter based on user's personality.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param channel_id: Discord channel ID
        :return: Conversation starter message or None
        """
        try:
            # Check if we should initiate conversation
            if random.random() > self.conversation_initiation_chance:
                return None
            
            # Get recent channel activity to avoid interrupting
            # This would need to be implemented with channel history checking
            
            # Generate conversation starter
            profile = await self.get_personality_profile(user_id, server_id)
            if not profile:
                return None
            
            starter_prompts = [
                "Start a casual conversation as you would naturally.",
                "Say something interesting to get people talking.",
                "Share a thought or ask a question to engage others.",
                "Begin a conversation in your typical style."
            ]
            
            prompt = random.choice(starter_prompts)
            
            response = await self.ollama.generate_response(
                model_name=profile['model_name'],
                prompt=prompt,
                max_tokens=150,
                temperature=0.9
            )
            
            if response and self.validate_model_response(response):
                return self._post_process_response(response)
            
            return None
            
        except Exception as e:
            print(f"Error initiating conversation for user {user_id}: {e}")
            return None
    
    async def update_personality_profile(
        self, 
        user_id: int, 
        server_id: int, 
        new_messages: List[Dict]
    ) -> bool:
        """
        Update personality profile with new message data.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param new_messages: New messages to incorporate
        :return: True if update successful, False otherwise
        """
        # This would require retraining the model with additional data
        # For now, return False to indicate updates are not yet supported
        return False
    
    def validate_model_response(self, response: str) -> bool:
        """
        Validate that a model response is appropriate.
        
        :param response: Generated response to validate
        :return: True if response is valid, False otherwise
        """
        if not response or len(response.strip()) == 0:
            return False
        
        # Check length limits
        if len(response) > self.max_response_length:
            return False
        
        # Check for minimum length
        if len(response.strip()) < 2:
            return False
        
        # Check for excessive repetition
        words = response.split()
        if len(words) > 1:
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.3:  # Less than 30% unique words
                return False
        
        # Check for common AI artifacts
        ai_artifacts = [
            "[INST]", "[/INST]", "<|", "|>", "###", "```",
            "I don't have", "I cannot", "As an AI", "I'm an AI"
        ]
        
        response_lower = response.lower()
        for artifact in ai_artifacts:
            if artifact.lower() in response_lower:
                return False
        
        return True
    
    async def get_training_status(self, user_id: int, server_id: int) -> Dict:
        """
        Get the current training status for a personality profile.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: Dictionary containing training status information
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT training_status, training_progress, started_at, 
                       completed_at, error_message, model_path
                FROM echo_profiles 
                WHERE user_id = ? AND server_id = ?
            """, (str(user_id), str(server_id)))
            
            result = await cursor.fetchone()
            if not result:
                return {
                    "status": "not_started",
                    "progress": 0,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                    "model_path": None
                }
            
            return {
                "status": result[0] or "not_started",
                "progress": result[1] or 0,
                "started_at": result[2],
                "completed_at": result[3],
                "error_message": result[4],
                "model_path": result[5]
            }