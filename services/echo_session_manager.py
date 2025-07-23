""""
Echo session management service for Echo bot.

Handles active echo sessions, session limits, and session lifecycle management.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiosqlite

from utils.validation import validate_discord_id


class EchoSessionManager:
    """
    Service for managing active echo sessions.
    
    This service handles:
    - Session creation and termination
    - Session state tracking
    - Server-wide session limits
    - Session monitoring and cleanup
    """
    
    def __init__(self, db_path: str, config: Dict):
        self.db_path = db_path
        self.config = config.get('echo', {})
        self.max_sessions_per_server = self.config.get('max_active_sessions_per_server', 5)
        self._active_sessions = {}  # Track active sessions in memory
    
    async def get_available_echoes(self, server_id: int) -> List[Dict]:
        """
        Get all available echo profiles for a server.
        
        :param server_id: Discord server ID
        :return: List of available echo profile dictionaries
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT user_id, training_status, created_at, total_messages
                FROM echo_profiles 
                WHERE server_id = ? AND training_status = 'completed'
                ORDER BY created_at DESC
            """, (str(server_id),))
            
            results = await cursor.fetchall()
            
            available_echoes = []
            for user_id, status, created_at, total_messages in results:
                available_echoes.append({
                    'user_id': user_id,
                    'status': status,
                    'created_at': created_at,
                    'total_messages': total_messages or 0
                })
            
            return available_echoes
    
    async def has_echo_profile(self, user_id: int, server_id: int) -> bool:
        """
        Check if an echo profile exists for a user.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: True if profile exists and is ready, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id FROM echo_profiles 
                WHERE user_id = ? AND server_id = ? AND training_status = 'completed'
            """, (str(user_id), str(server_id)))
            
            result = await cursor.fetchone()
            return result is not None
    
    async def is_echo_active(self, user_id: int, channel_id: int) -> bool:
        """
        Check if an echo is currently active in a channel.
        
        :param user_id: Discord user ID
        :param channel_id: Discord channel ID
        :return: True if echo is active, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT es.id FROM echo_sessions es
                JOIN echo_profiles ep ON es.profile_id = ep.id
                WHERE ep.user_id = ? AND es.channel_id = ? AND es.is_active = 1
            """, (str(user_id), str(channel_id)))
            
            result = await cursor.fetchone()
            return result is not None
    
    async def can_start_new_session(self, server_id: int) -> bool:
        """
        Check if a new echo session can be started in the server.
        
        :param server_id: Discord server ID
        :return: True if new session can be started, False if limit reached
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT COUNT(*) FROM echo_sessions 
                WHERE server_id = ? AND is_active = 1
            """, (str(server_id),))
            
            result = await cursor.fetchone()
            current_sessions = result[0] if result else 0
            
            return current_sessions < self.max_sessions_per_server
    
    async def start_echo_session(
        self, 
        user_id: int, 
        channel_id: int, 
        server_id: int,
        requester_id: int
    ) -> Dict:
        """
        Start a new echo session.
        
        :param user_id: Discord user ID for the echo
        :param channel_id: Discord channel ID
        :param server_id: Discord server ID
        :param requester_id: ID of user who started the session
        :return: Dictionary containing session information
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get the echo profile
            cursor = await db.execute("""
                SELECT id FROM echo_profiles 
                WHERE user_id = ? AND server_id = ? AND training_status = 'completed'
            """, (str(user_id), str(server_id)))
            
            profile_result = await cursor.fetchone()
            if not profile_result:
                raise Exception("Echo profile not found or not ready")
            
            profile_id = profile_result[0]
            
            # Stop any existing session in this channel
            await db.execute("""
                UPDATE echo_sessions 
                SET is_active = 0, stopped_at = ?
                WHERE channel_id = ? AND is_active = 1
            """, (datetime.now(), str(channel_id)))
            
            # Create new session
            cursor = await db.execute("""
                INSERT INTO echo_sessions 
                (profile_id, channel_id, server_id, requester_id, is_active, started_at, last_activity)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (
                profile_id, str(channel_id), str(server_id), 
                str(requester_id), datetime.now(), datetime.now()
            ))
            
            session_id = cursor.lastrowid
            await db.commit()
            
            # Add to active sessions tracking
            session_key = f"{server_id}_{channel_id}"
            self._active_sessions[session_key] = {
                "session_id": session_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "server_id": server_id,
                "requester_id": requester_id,
                "started_at": datetime.now(),
                "status": "active"
            }
            
            return self._active_sessions[session_key]
    
    async def get_active_echo(self, channel_id: int) -> Optional[Dict]:
        """
        Get the currently active echo in a channel.
        
        :param channel_id: Discord channel ID
        :return: Active echo session info or None if no active echo
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT es.id, ep.user_id, es.server_id, es.requester_id, 
                       es.started_at, es.messages_generated
                FROM echo_sessions es
                JOIN echo_profiles ep ON es.profile_id = ep.id
                WHERE es.channel_id = ? AND es.is_active = 1
            """, (str(channel_id),))
            
            result = await cursor.fetchone()
            if not result:
                return None
            
            return {
                "session_id": result[0],
                "user_id": result[1],
                "server_id": result[2],
                "channel_id": channel_id,
                "requester_id": result[3],
                "started_at": result[4],
                "messages_generated": result[5] or 0,
                "status": "active"
            }
    
    async def stop_echo_session(self, channel_id: int, requester_id: int) -> bool:
        """
        Stop the echo session in a channel.
        
        :param channel_id: Discord channel ID
        :param requester_id: ID of user stopping the session
        :return: True if session was stopped, False if no active session
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Update session to inactive
            cursor = await db.execute("""
                UPDATE echo_sessions 
                SET is_active = 0, stopped_at = ?
                WHERE channel_id = ? AND is_active = 1
            """, (datetime.now(), str(channel_id)))
            
            rows_affected = cursor.rowcount
            await db.commit()
            
            # Remove from active sessions tracking
            for key in list(self._active_sessions.keys()):
                if key.endswith(f"_{channel_id}"):
                    del self._active_sessions[key]
                    break
            
            return rows_affected > 0
    
    async def get_server_stats(self, server_id: int) -> Dict:
        """
        Get echo statistics for a server.
        
        :param server_id: Discord server ID
        :return: Dictionary containing server statistics
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get profile counts
            cursor = await db.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN training_status = 'completed' THEN 1 ELSE 0 END) as ready,
                    SUM(CASE WHEN training_status = 'in_progress' THEN 1 ELSE 0 END) as training
                FROM echo_profiles 
                WHERE server_id = ?
            """, (str(server_id),))
            
            profile_stats = await cursor.fetchone()
            
            # Get active session count
            cursor = await db.execute("""
                SELECT COUNT(*) FROM echo_sessions 
                WHERE server_id = ? AND is_active = 1
            """, (str(server_id),))
            
            active_sessions_result = await cursor.fetchone()
            active_sessions = active_sessions_result[0] if active_sessions_result else 0
            
            # Get active echoes details
            cursor = await db.execute("""
                SELECT ep.user_id, es.channel_id
                FROM echo_sessions es
                JOIN echo_profiles ep ON es.profile_id = ep.id
                WHERE es.server_id = ? AND es.is_active = 1
            """, (str(server_id),))
            
            active_echoes_results = await cursor.fetchall()
            active_echoes = [
                {"user_id": user_id, "channel_id": channel_id}
                for user_id, channel_id in active_echoes_results
            ]
            
            return {
                "total_profiles": profile_stats[0] if profile_stats else 0,
                "ready_profiles": profile_stats[1] if profile_stats else 0,
                "training_profiles": profile_stats[2] if profile_stats else 0,
                "active_sessions": active_sessions,
                "max_sessions": self.max_sessions_per_server,
                "active_echoes": active_echoes
            }
    
    async def get_session_history(self, user_id: int, server_id: int) -> List[Dict]:
        """
        Get session history for a user's echo.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: List of historical session information
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT es.id, es.channel_id, es.requester_id, es.started_at, 
                       es.stopped_at, es.messages_generated, es.conversations_started
                FROM echo_sessions es
                JOIN echo_profiles ep ON es.profile_id = ep.id
                WHERE ep.user_id = ? AND es.server_id = ?
                ORDER BY es.started_at DESC
                LIMIT 50
            """, (str(user_id), str(server_id)))
            
            results = await cursor.fetchall()
            
            history = []
            for result in results:
                history.append({
                    "session_id": result[0],
                    "channel_id": result[1],
                    "requester_id": result[2],
                    "started_at": result[3],
                    "stopped_at": result[4],
                    "messages_generated": result[5] or 0,
                    "conversations_started": result[6] or 0
                })
            
            return history
    
    async def cleanup_inactive_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up sessions that have been inactive for too long.
        
        :param max_age_hours: Maximum age for inactive sessions
        :return: Number of sessions cleaned up
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        async with aiosqlite.connect(self.db_path) as db:
            # Find inactive sessions
            cursor = await db.execute("""
                SELECT id, channel_id FROM echo_sessions 
                WHERE is_active = 1 AND last_activity < ?
            """, (cutoff_time,))
            
            inactive_sessions = await cursor.fetchall()
            
            if not inactive_sessions:
                return 0
            
            # Mark sessions as inactive
            session_ids = [str(session[0]) for session in inactive_sessions]
            placeholders = ",".join(["?" for _ in session_ids])
            
            await db.execute(f"""
                UPDATE echo_sessions 
                SET is_active = 0, stopped_at = ?
                WHERE id IN ({placeholders})
            """, [datetime.now()] + session_ids)
            
            await db.commit()
            
            # Clean up from active sessions tracking
            for session_id, channel_id in inactive_sessions:
                for key in list(self._active_sessions.keys()):
                    if key.endswith(f"_{channel_id}"):
                        del self._active_sessions[key]
                        break
            
            return len(inactive_sessions)
    
    async def get_user_sessions(self, user_id: int) -> List[Dict]:
        """
        Get all active sessions for a user across all servers.
        
        :param user_id: Discord user ID
        :return: List of active session information
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT es.id, es.channel_id, es.server_id, es.started_at, es.messages_generated
                FROM echo_sessions es
                JOIN echo_profiles ep ON es.profile_id = ep.id
                WHERE ep.user_id = ? AND es.is_active = 1
            """, (str(user_id),))
            
            results = await cursor.fetchall()
            
            sessions = []
            for result in results:
                sessions.append({
                    "session_id": result[0],
                    "channel_id": result[1],
                    "server_id": result[2],
                    "started_at": result[3],
                    "messages_generated": result[4] or 0
                })
            
            return sessions
    
    async def force_stop_user_sessions(self, user_id: int, server_id: int) -> int:
        """
        Force stop all sessions for a user in a server.
        
        :param user_id: Discord user ID
        :param server_id: Discord server ID
        :return: Number of sessions stopped
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get active sessions for this user
            cursor = await db.execute("""
                SELECT es.id, es.channel_id
                FROM echo_sessions es
                JOIN echo_profiles ep ON es.profile_id = ep.id
                WHERE ep.user_id = ? AND es.server_id = ? AND es.is_active = 1
            """, (str(user_id), str(server_id)))
            
            active_sessions = await cursor.fetchall()
            
            if not active_sessions:
                return 0
            
            # Stop all sessions
            session_ids = [str(session[0]) for session in active_sessions]
            placeholders = ",".join(["?" for _ in session_ids])
            
            cursor = await db.execute(f"""
                UPDATE echo_sessions 
                SET is_active = 0, stopped_at = ?
                WHERE id IN ({placeholders})
            """, [datetime.now()] + session_ids)
            
            rows_affected = cursor.rowcount
            await db.commit()
            
            # Clean up from active sessions tracking
            for session_id, channel_id in active_sessions:
                for key in list(self._active_sessions.keys()):
                    if key.endswith(f"_{channel_id}"):
                        del self._active_sessions[key]
                        break
            
            return rows_affected
    
    async def get_session_metrics(self, session_id: int) -> Dict:
        """
        Get metrics for a specific session.
        
        :param session_id: Session ID
        :return: Dictionary containing session metrics
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT messages_generated, conversations_started, started_at, stopped_at
                FROM echo_sessions 
                WHERE id = ?
            """, (session_id,))
            
            result = await cursor.fetchone()
            if not result:
                return {
                    "messages_generated": 0,
                    "conversations_started": 0,
                    "average_response_time": 0.0,
                    "uptime_seconds": 0,
                    "errors": 0
                }
            
            messages_generated, conversations_started, started_at, stopped_at = result
            
            # Calculate uptime
            if started_at:
                start_time = datetime.fromisoformat(started_at) if isinstance(started_at, str) else started_at
                end_time = datetime.fromisoformat(stopped_at) if stopped_at and isinstance(stopped_at, str) else (stopped_at or datetime.now())
                uptime_seconds = (end_time - start_time).total_seconds()
            else:
                uptime_seconds = 0
            
            # Get response time data (would need to be tracked in echo_responses table)
            cursor = await db.execute("""
                SELECT AVG(generation_time_ms) FROM echo_responses 
                WHERE session_id = ?
            """, (session_id,))
            
            avg_response_time_result = await cursor.fetchone()
            avg_response_time = avg_response_time_result[0] if avg_response_time_result and avg_response_time_result[0] else 0.0
            
            return {
                "messages_generated": messages_generated or 0,
                "conversations_started": conversations_started or 0,
                "average_response_time": avg_response_time / 1000.0 if avg_response_time else 0.0,  # Convert to seconds
                "uptime_seconds": uptime_seconds,
                "errors": 0  # Would need error tracking implementation
            }
    
    async def update_session_activity(self, channel_id: int) -> None:
        """
        Update the last activity timestamp for a session.
        
        :param channel_id: Discord channel ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE echo_sessions 
                SET last_activity = ?
                WHERE channel_id = ? AND is_active = 1
            """, (datetime.now(), str(channel_id)))
            await db.commit()
    
    async def increment_session_stats(
        self, 
        channel_id: int, 
        messages_generated: int = 0, 
        conversations_started: int = 0
    ) -> None:
        """
        Increment session statistics.
        
        :param channel_id: Discord channel ID
        :param messages_generated: Number of messages to add to count
        :param conversations_started: Number of conversations to add to count
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE echo_sessions 
                SET messages_generated = messages_generated + ?,
                    conversations_started = conversations_started + ?,
                    last_activity = ?
                WHERE channel_id = ? AND is_active = 1
            """, (messages_generated, conversations_started, datetime.now(), str(channel_id)))
            await db.commit()