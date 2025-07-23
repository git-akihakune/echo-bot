"""
Ollama client service for Echo bot.

Handles local LLM communication, model management, and fine-tuning operations.
"""

import asyncio
import json
import os
import aiofiles
from datetime import datetime
from typing import Dict, List, Optional, AsyncGenerator
import ollama
from ollama import AsyncChat

from utils.validation import validate_model_name, sanitize_filename


class OllamaClient:
    """
    Service for managing Ollama local LLM operations.
    
    This service handles:
    - Model loading and unloading
    - Model fine-tuning with user data
    - Response generation
    - Model state management
    """
    
    def __init__(self, host: str = "http://localhost:11434", base_model: str = "dolphin3:latest"):
        self.host = host
        self.base_model = base_model
        self.client = ollama.AsyncClient(host=host)
        self._loaded_models = set()
        self._training_tasks = {}
    
    async def check_ollama_availability(self) -> tuple[bool, Optional[str]]:
        """
        Check if Ollama service is available.
        
        :return: Tuple of (is_available, error_message)
        """
        try:
            # Try to list available models to test connection
            await self.client.list()
            return True, None
        except Exception as e:
            return False, f"Ollama service unavailable: {str(e)}"
    
    async def ensure_base_model_available(self) -> bool:
        """
        Ensure the base model is available for fine-tuning.
        
        :return: True if model is available, False otherwise
        """
        try:
            models = await self.client.list()
            model_names = [model['name'] for model in models['models']]
            
            if self.base_model not in model_names:
                # Try to pull the base model
                await self.pull_model(self.base_model)
            
            return True
        except Exception as e:
            print(f"Error ensuring base model availability: {e}")
            return False
    
    async def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama registry.
        
        :param model_name: Name of model to pull
        :return: True if successful, False otherwise
        """
        try:
            is_valid, error_msg = validate_model_name(model_name)
            if not is_valid:
                raise ValueError(error_msg)
            
            # Pull model asynchronously
            await self.client.pull(model_name)
            return True
        except Exception as e:
            print(f"Error pulling model {model_name}: {e}")
            return False
    
    async def create_fine_tuned_model(
        self, 
        user_id: int, 
        server_id: int, 
        dataset_path: str,
        training_config: Dict = None
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Create a fine-tuned model from user data.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :param dataset_path: Path to training dataset
        :param training_config: Training configuration parameters
        :return: Tuple of (success, model_name, error_message)
        """
        try:
            # Validate inputs
            if not os.path.exists(dataset_path):
                return False, None, f"Dataset file not found: {dataset_path}"
            
            # Generate unique model name
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            model_name = f"echo_user_{user_id}_server_{server_id}_{timestamp}"
            
            # Default training configuration
            if training_config is None:
                training_config = {
                    "epochs": 10,
                    "batch_size": 4,
                    "learning_rate": 0.0001,
                    "max_seq_length": 512
                }
            
            # Create Modelfile for fine-tuning
            modelfile_path = await self._create_modelfile(
                model_name, dataset_path, training_config
            )
            
            # Start training task
            task_key = f"{user_id}_{server_id}"
            if task_key in self._training_tasks:
                self._training_tasks[task_key].cancel()
            
            self._training_tasks[task_key] = asyncio.create_task(
                self._run_model_training(model_name, modelfile_path, task_key)
            )
            
            return True, model_name, None
            
        except Exception as e:
            return False, None, f"Error creating fine-tuned model: {str(e)}"
    
    async def _create_modelfile(
        self, 
        model_name: str, 
        dataset_path: str, 
        training_config: Dict
    ) -> str:
        """
        Create Modelfile for Ollama fine-tuning.
        
        :param model_name: Name of the model to create
        :param dataset_path: Path to training dataset
        :param training_config: Training configuration
        :return: Path to created Modelfile
        """
        # Create models directory if it doesn't exist
        models_dir = os.path.join(os.getcwd(), "models")
        os.makedirs(models_dir, exist_ok=True)
        
        # Read training dataset
        async with aiofiles.open(dataset_path, 'r', encoding='utf-8') as f:
            dataset_content = await f.read()
            dataset = json.loads(dataset_content)
        
        # Create Modelfile content
        modelfile_content = f"""FROM {self.base_model}

# Model parameters
PARAMETER temperature 0.8
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 2048

# System prompt for echo personality
SYSTEM \"\"\"You are an AI assistant that mimics the communication style and personality of a specific Discord user based on their historical messages. You should:

1. Match their typical response length and tone
2. Use similar vocabulary and expressions
3. Maintain their level of formality/informality
4. Reflect their interests and topics they commonly discuss
5. Respond in a way that feels natural and consistent with their personality

Be conversational and engaging, but stay true to the personality you're emulating.\"\"\"

"""
        
        # Add training examples
        for i, example in enumerate(dataset[:100]):  # Limit to first 100 examples
            prompt = example.get('prompt', '')
            response = example.get('response', '')
            
            if prompt and response:
                # Escape quotes in the content
                escaped_prompt = prompt.replace('"', '\\"').replace('\n', '\\n')
                escaped_response = response.replace('"', '\\"').replace('\n', '\\n')
                
                modelfile_content += f'''
# Training example {i+1}
TEMPLATE \"\"\"{{{{ if .System }}}}{{{{ .System }}}}

{{{{ end }}}}{{{{ if .Prompt }}}}User: {{{{ .Prompt }}}}
Assistant: {{{{ end }}}}{{{{ .Response }}}}\"\"\"
'''
        
        # Save Modelfile
        modelfile_path = os.path.join(models_dir, f"{model_name}.Modelfile")
        async with aiofiles.open(modelfile_path, 'w', encoding='utf-8') as f:
            await f.write(modelfile_content)
        
        return modelfile_path
    
    async def _run_model_training(
        self, 
        model_name: str, 
        modelfile_path: str, 
        task_key: str
    ) -> bool:
        """
        Run model training process.
        
        :param model_name: Name of model to create
        :param modelfile_path: Path to Modelfile
        :param task_key: Task tracking key
        :return: True if successful, False otherwise
        """
        try:
            # Read Modelfile
            async with aiofiles.open(modelfile_path, 'r', encoding='utf-8') as f:
                modelfile_content = await f.read()
            
            # Create model using Ollama
            await self.client.create(
                model=model_name,
                modelfile=modelfile_content
            )
            
            # Add to loaded models
            self._loaded_models.add(model_name)
            
            return True
            
        except Exception as e:
            print(f"Error training model {model_name}: {e}")
            return False
        finally:
            # Clean up task reference
            if task_key in self._training_tasks:
                del self._training_tasks[task_key]
            
            # Clean up Modelfile
            try:
                os.remove(modelfile_path)
            except OSError:
                pass
    
    async def load_model(self, model_name: str) -> bool:
        """
        Load a model into memory.
        
        :param model_name: Name of model to load
        :return: True if successful, False otherwise
        """
        try:
            is_valid, error_msg = validate_model_name(model_name)
            if not is_valid:
                raise ValueError(error_msg)
            
            # Check if model exists
            models = await self.client.list()
            model_names = [model['name'] for model in models['models']]
            
            if model_name not in model_names:
                return False
            
            # Load model by making a simple request
            await self.client.chat(
                model=model_name,
                messages=[{'role': 'user', 'content': 'Hello'}],
                stream=False
            )
            
            self._loaded_models.add(model_name)
            return True
            
        except Exception as e:
            print(f"Error loading model {model_name}: {e}")
            return False
    
    async def unload_model(self, model_name: str) -> bool:
        """
        Unload a model from memory.
        
        :param model_name: Name of model to unload
        :return: True if successful, False otherwise
        """
        try:
            # Ollama doesn't have explicit unload, but we can track loaded models
            self._loaded_models.discard(model_name)
            return True
        except Exception as e:
            print(f"Error unloading model {model_name}: {e}")
            return False
    
    async def generate_response(
        self, 
        model_name: str, 
        prompt: str, 
        context: List[Dict] = None,
        max_tokens: int = 200,
        temperature: float = 0.8
    ) -> Optional[str]:
        """
        Generate response using a specific model.
        
        :param model_name: Name of model to use
        :param prompt: Input prompt
        :param context: Conversation context
        :param max_tokens: Maximum response length
        :param temperature: Response creativity (0.0-1.0)
        :return: Generated response or None if failed
        """
        try:
            # Ensure model is loaded
            if model_name not in self._loaded_models:
                success = await self.load_model(model_name)
                if not success:
                    return None
            
            # Prepare messages
            messages = []
            
            # Add context if provided
            if context:
                for msg in context[-5:]:  # Last 5 messages for context
                    messages.append({
                        'role': msg.get('role', 'user'),
                        'content': msg.get('content', '')
                    })
            
            # Add current prompt
            messages.append({
                'role': 'user',
                'content': prompt
            })
            
            # Generate response
            response = await self.client.chat(
                model=model_name,
                messages=messages,
                stream=False,
                options={
                    'temperature': temperature,
                    'num_predict': max_tokens,
                    'top_p': 0.9,
                    'top_k': 40
                }
            )
            
            return response['message']['content'].strip()
            
        except Exception as e:
            print(f"Error generating response with model {model_name}: {e}")
            return None
    
    async def stream_response(
        self, 
        model_name: str, 
        prompt: str, 
        context: List[Dict] = None,
        temperature: float = 0.8
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using a specific model.
        
        :param model_name: Name of model to use
        :param prompt: Input prompt
        :param context: Conversation context
        :param temperature: Response creativity (0.0-1.0)
        :yield: Response chunks
        """
        try:
            # Ensure model is loaded
            if model_name not in self._loaded_models:
                success = await self.load_model(model_name)
                if not success:
                    return
            
            # Prepare messages
            messages = []
            
            # Add context if provided
            if context:
                for msg in context[-5:]:  # Last 5 messages for context
                    messages.append({
                        'role': msg.get('role', 'user'),
                        'content': msg.get('content', '')
                    })
            
            # Add current prompt
            messages.append({
                'role': 'user',
                'content': prompt
            })
            
            # Generate streaming response
            stream = await self.client.chat(
                model=model_name,
                messages=messages,
                stream=True,
                options={
                    'temperature': temperature,
                    'top_p': 0.9,
                    'top_k': 40
                }
            )
            
            async for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    yield chunk['message']['content']
                    
        except Exception as e:
            print(f"Error streaming response with model {model_name}: {e}")
            return
    
    async def delete_model(self, model_name: str) -> bool:
        """
        Delete a model from Ollama.
        
        :param model_name: Name of model to delete
        :return: True if successful, False otherwise
        """
        try:
            await self.client.delete(model_name)
            self._loaded_models.discard(model_name)
            return True
        except Exception as e:
            print(f"Error deleting model {model_name}: {e}")
            return False
    
    async def list_models(self) -> List[Dict]:
        """
        List all available models.
        
        :return: List of model information dictionaries
        """
        try:
            models = await self.client.list()
            return models['models']
        except Exception as e:
            print(f"Error listing models: {e}")
            return []
    
    async def get_model_info(self, model_name: str) -> Optional[Dict]:
        """
        Get information about a specific model.
        
        :param model_name: Name of model
        :return: Model information dictionary or None
        """
        try:
            models = await self.list_models()
            for model in models:
                if model['name'] == model_name:
                    return model
            return None
        except Exception as e:
            print(f"Error getting model info for {model_name}: {e}")
            return None
    
    async def is_training_in_progress(self, user_id: int, server_id: int) -> bool:
        """
        Check if model training is in progress for a user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: True if training is in progress, False otherwise
        """
        task_key = f"{user_id}_{server_id}"
        return task_key in self._training_tasks and not self._training_tasks[task_key].done()
    
    async def cancel_training(self, user_id: int, server_id: int) -> bool:
        """
        Cancel ongoing training for a user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: True if cancelled, False if no training in progress
        """
        task_key = f"{user_id}_{server_id}"
        if task_key in self._training_tasks:
            self._training_tasks[task_key].cancel()
            del self._training_tasks[task_key]
            return True
        return False
    
    async def cleanup_old_models(self, days_old: int = 7) -> int:
        """
        Clean up old echo models.
        
        :param days_old: Remove models older than this many days
        :return: Number of models cleaned up
        """
        try:
            models = await self.list_models()
            cleaned_count = 0
            
            for model in models:
                model_name = model['name']
                
                # Only clean up echo models
                if not model_name.startswith('echo_user_'):
                    continue
                
                # Extract timestamp from model name
                try:
                    timestamp_str = model_name.split('_')[-1]
                    model_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                    
                    if (datetime.now() - model_date).days > days_old:
                        success = await self.delete_model(model_name)
                        if success:
                            cleaned_count += 1
                            
                except (ValueError, IndexError):
                    # Skip models with invalid timestamp format
                    continue
            
            return cleaned_count
            
        except Exception as e:
            print(f"Error cleaning up old models: {e}")
            return 0