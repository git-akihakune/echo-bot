"""
Background task management for Echo bot.

Handles long-running operations like cleanup tasks and periodic maintenance.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
from discord.ext import tasks, commands


class BackgroundTaskManager:
    """
    Service for managing background tasks and periodic operations.
    
    This service handles:
    - Periodic cleanup of old data
    - Session monitoring and cleanup
    - Model cleanup and maintenance
    - Health checks and monitoring
    """
    
    def __init__(self, bot: commands.Bot, message_processor, personality_engine, session_manager):
        self.bot = bot
        self.message_processor = message_processor
        self.personality_engine = personality_engine
        self.session_manager = session_manager
        
        # Task status tracking
        self._tasks_running = False
        self._last_cleanup = None
        self._cleanup_stats = {
            "last_run": None,
            "sessions_cleaned": 0,
            "data_cleaned": 0,
            "models_cleaned": 0
        }
    
    def start_background_tasks(self) -> None:
        """Start all background tasks."""
        if not self._tasks_running:
            self.cleanup_task.start()
            self.session_monitor_task.start()
            self._tasks_running = True
            print("Background tasks started")
    
    def stop_background_tasks(self) -> None:
        """Stop all background tasks."""
        if self._tasks_running:
            self.cleanup_task.cancel()
            self.session_monitor_task.cancel()
            self._tasks_running = False
            print("Background tasks stopped")
    
    @tasks.loop(hours=24)  # Run daily
    async def cleanup_task(self) -> None:
        """Periodic cleanup task."""
        try:
            print("Starting daily cleanup task...")
            
            # Clean up old message data (30 days old)
            data_cleaned = await self.message_processor.cleanup_old_data(days_old=30)
            
            # Clean up old models (7 days old)
            models_cleaned = await self.personality_engine.ollama.cleanup_old_models(days_old=7)
            
            # Update cleanup stats
            self._cleanup_stats.update({
                "last_run": datetime.now(),
                "data_cleaned": data_cleaned,
                "models_cleaned": models_cleaned
            })
            
            print(f"Daily cleanup completed - Data: {data_cleaned}, Models: {models_cleaned}")
            
        except Exception as e:
            print(f"Error in cleanup task: {e}")
    
    @tasks.loop(hours=1)  # Run hourly
    async def session_monitor_task(self) -> None:
        """Monitor and cleanup inactive sessions."""
        try:
            # Clean up sessions inactive for more than 24 hours
            sessions_cleaned = await self.session_manager.cleanup_inactive_sessions(max_age_hours=24)
            
            if sessions_cleaned > 0:
                self._cleanup_stats["sessions_cleaned"] = sessions_cleaned
                print(f"Cleaned up {sessions_cleaned} inactive sessions")
                
        except Exception as e:
            print(f"Error in session monitor task: {e}")
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self) -> None:
        """Wait for bot to be ready before starting cleanup task."""
        await self.bot.wait_until_ready()
    
    @session_monitor_task.before_loop
    async def before_session_monitor_task(self) -> None:
        """Wait for bot to be ready before starting session monitor task."""
        await self.bot.wait_until_ready()
    
    async def manual_cleanup(self, cleanup_type: str = "all") -> Dict:
        """
        Manually trigger cleanup operations.
        
        :param cleanup_type: Type of cleanup ("all", "data", "sessions", "models")
        :return: Dictionary with cleanup results
        """
        results = {}
        
        try:
            if cleanup_type in ["all", "data"]:
                results["data_cleaned"] = await self.message_processor.cleanup_old_data(days_old=30)
            
            if cleanup_type in ["all", "sessions"]:
                results["sessions_cleaned"] = await self.session_manager.cleanup_inactive_sessions(max_age_hours=24)
            
            if cleanup_type in ["all", "models"]:
                results["models_cleaned"] = await self.personality_engine.ollama.cleanup_old_models(days_old=7)
            
            results["success"] = True
            results["timestamp"] = datetime.now()
            
        except Exception as e:
            results["success"] = False
            results["error"] = str(e)
            results["timestamp"] = datetime.now()
        
        return results
    
    async def get_task_status(self) -> Dict:
        """
        Get status of background tasks.
        
        :return: Dictionary containing task status information
        """
        return {
            "tasks_running": self._tasks_running,
            "cleanup_task_running": not self.cleanup_task.is_being_cancelled() if hasattr(self, 'cleanup_task') else False,
            "session_monitor_running": not self.session_monitor_task.is_being_cancelled() if hasattr(self, 'session_monitor_task') else False,
            "last_cleanup_stats": self._cleanup_stats,
            "next_cleanup": self.cleanup_task.next_iteration if hasattr(self, 'cleanup_task') and not self.cleanup_task.is_being_cancelled() else None,
            "next_session_monitor": self.session_monitor_task.next_iteration if hasattr(self, 'session_monitor_task') and not self.session_monitor_task.is_being_cancelled() else None
        }
    
    async def restart_task(self, task_name: str) -> bool:
        """
        Restart a specific background task.
        
        :param task_name: Name of task to restart ("cleanup" or "session_monitor")
        :return: True if successful, False otherwise
        """
        try:
            if task_name == "cleanup":
                if hasattr(self, 'cleanup_task'):
                    self.cleanup_task.cancel()
                    await asyncio.sleep(1)  # Give time for cancellation
                    self.cleanup_task.start()
                    return True
            
            elif task_name == "session_monitor":
                if hasattr(self, 'session_monitor_task'):
                    self.session_monitor_task.cancel()
                    await asyncio.sleep(1)  # Give time for cancellation
                    self.session_monitor_task.start()
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error restarting task {task_name}: {e}")
            return False
    
    async def health_check(self) -> Dict:
        """
        Perform health check on all services.
        
        :return: Dictionary containing health check results
        """
        health_status = {
            "timestamp": datetime.now(),
            "overall_status": "healthy",
            "services": {}
        }
        
        try:
            # Check Ollama availability
            ollama_available, ollama_error = await self.personality_engine.ollama.check_ollama_availability()
            health_status["services"]["ollama"] = {
                "status": "healthy" if ollama_available else "unhealthy",
                "error": ollama_error if not ollama_available else None
            }
            
            # Check database connectivity
            try:
                import aiosqlite
                async with aiosqlite.connect(self.message_processor.db_path) as db:
                    await db.execute("SELECT 1")
                health_status["services"]["database"] = {"status": "healthy"}
            except Exception as db_error:
                health_status["services"]["database"] = {
                    "status": "unhealthy",
                    "error": str(db_error)
                }
            
            # Check background tasks
            health_status["services"]["background_tasks"] = {
                "status": "healthy" if self._tasks_running else "stopped",
                "cleanup_running": not self.cleanup_task.is_being_cancelled() if hasattr(self, 'cleanup_task') else False,
                "monitor_running": not self.session_monitor_task.is_being_cancelled() if hasattr(self, 'session_monitor_task') else False
            }
            
            # Determine overall status
            unhealthy_services = [
                service for service, status in health_status["services"].items()
                if status["status"] == "unhealthy"
            ]
            
            if unhealthy_services:
                health_status["overall_status"] = "unhealthy"
                health_status["unhealthy_services"] = unhealthy_services
            
        except Exception as e:
            health_status["overall_status"] = "error"
            health_status["error"] = str(e)
        
        return health_status
    
    async def get_system_stats(self) -> Dict:
        """
        Get system statistics and metrics.
        
        :return: Dictionary containing system statistics
        """
        try:
            stats = {
                "timestamp": datetime.now(),
                "bot": {
                    "guilds": len(self.bot.guilds),
                    "users": len(self.bot.users),
                    "uptime_seconds": (datetime.now() - self.bot.launch_time).total_seconds() if hasattr(self.bot, 'launch_time') else 0
                },
                "echo": {
                    "total_profiles": 0,
                    "active_sessions": 0,
                    "total_messages_processed": 0
                },
                "background_tasks": await self.get_task_status()
            }
            
            # Get echo statistics across all servers
            for guild in self.bot.guilds:
                try:
                    server_stats = await self.session_manager.get_server_stats(guild.id)
                    stats["echo"]["total_profiles"] += server_stats["total_profiles"]
                    stats["echo"]["active_sessions"] += server_stats["active_sessions"]
                except Exception:
                    continue  # Skip if server stats fail
            
            return stats
            
        except Exception as e:
            return {
                "timestamp": datetime.now(),
                "error": str(e),
                "status": "error"
            }