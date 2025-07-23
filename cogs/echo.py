""""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 6.1.0
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from datetime import datetime

# Import services
from services.message_processor import MessageProcessor
from services.personality_engine import PersonalityEngine
from services.echo_session_manager import EchoSessionManager
import os


class Echo(commands.Cog, name="echo"):
    def __init__(self, bot) -> None:
        self.bot = bot
        
        # Get database path
        db_path = f"{os.path.realpath(os.path.dirname(__file__))}/../database/database.db"
        
        # Initialize services
        self.message_processor = MessageProcessor(bot, db_path)
        self.personality_engine = PersonalityEngine(db_path, bot.config)
        self.session_manager = EchoSessionManager(db_path, bot.config)
        
        # Set up callback to trigger model training after message analysis
        self.message_processor.set_personality_engine_callback(
            self.personality_engine.create_personality_profile
        )

    @app_commands.command(
        name="analyze",
        description="Analyze a user's messages before a specified date to create an echo profile"
    )
    @app_commands.describe(
        user="The user to analyze",
        cutoff_date="Date in DD.MM.YYYY format (messages before this date will be analyzed)"
    )
    async def echo_analyze(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        cutoff_date: str
    ) -> None:
        """
        Analyze a user's messages before a cutoff date to create an echo profile.
        
        :param interaction: The application command interaction
        :param user: The Discord user to analyze
        :param cutoff_date: Date in DD.MM.YYYY format
        """
        await interaction.response.defer()
        
        try:
            # Parse and validate the date
            from utils.date_parser import parse_dd_mm_yyyy
            parsed_date = parse_dd_mm_yyyy(cutoff_date)
            
            # Check if user has permission to analyze this user
            if not await self._can_analyze_user(interaction, user):
                embed = discord.Embed(
                    title="Permission Denied",
                    description="You don't have permission to analyze this user.",
                    color=0xE02B2B
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Check if analysis is already in progress
            if await self.message_processor.is_analysis_in_progress(user.id, interaction.guild.id):
                embed = discord.Embed(
                    title="Analysis in Progress",
                    description=f"Analysis for {user.mention} is already in progress.",
                    color=0xE02B2B
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Start analysis process
            embed = discord.Embed(
                title="Starting Analysis",
                description=f"Starting analysis of {user.mention}'s messages before {cutoff_date}.\nThis may take a while...",
                color=0x9C84EF
            )
            await interaction.followup.send(embed=embed)
            
            # Start background analysis task
            await self.message_processor.start_analysis(
                user_id=user.id,
                server_id=interaction.guild.id,
                cutoff_date=parsed_date,
                requester_id=interaction.user.id
            )
            
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid Date Format",
                description=f"Please use DD.MM.YYYY format. Error: {str(e)}",
                color=0xE02B2B
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred while starting analysis: {str(e)}",
                color=0xE02B2B
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="online",
        description="Activate an echo bot in the current channel"
    )
    @app_commands.describe(
        user="The user whose echo should be activated (optional, shows available echoes if not specified)"
    )
    async def echo_online(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None
    ) -> None:
        """
        Activate an echo bot in the current channel.
        
        :param interaction: The application command interaction
        :param user: The user whose echo should be activated
        """
        await interaction.response.defer()
        
        try:
            # If no user specified, show available echoes
            if user is None:
                available_echoes = await self.session_manager.get_available_echoes(interaction.guild.id)
                if not available_echoes:
                    embed = discord.Embed(
                        title="No Echoes Available",
                        description="No echo profiles are available in this server. Use `/echo analyze` to create one.",
                        color=0xE02B2B
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Show available echoes
                embed = discord.Embed(
                    title="Available Echoes",
                    description="Select a user to activate their echo:",
                    color=0x9C84EF
                )
                for echo_info in available_echoes:
                    embed.add_field(
                        name=f"<@{echo_info['user_id']}>",
                        value=f"Created: {echo_info['created_at']}\nStatus: {echo_info['status']}",
                        inline=True
                    )
                await interaction.followup.send(embed=embed)
                return
            
            # Check if echo profile exists
            if not await self.session_manager.has_echo_profile(user.id, interaction.guild.id):
                embed = discord.Embed(
                    title="Echo Profile Not Found",
                    description=f"No echo profile found for {user.mention}. Use `/echo analyze` to create one.",
                    color=0xE02B2B
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Check if echo is already active in this channel
            if await self.session_manager.is_echo_active(user.id, interaction.channel.id):
                embed = discord.Embed(
                    title="Echo Already Active",
                    description=f"Echo for {user.mention} is already active in this channel.",
                    color=0xE02B2B
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Check server limits
            if not await self.session_manager.can_start_new_session(interaction.guild.id):
                embed = discord.Embed(
                    title="Session Limit Reached",
                    description="Maximum number of active echo sessions reached for this server.",
                    color=0xE02B2B
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Start echo session
            await self.session_manager.start_echo_session(
                user_id=user.id,
                channel_id=interaction.channel.id,
                server_id=interaction.guild.id,
                requester_id=interaction.user.id
            )
            
            embed = discord.Embed(
                title="Echo Activated",
                description=f"Echo for {user.mention} is now active in this channel.",
                color=0x9C84EF
            )
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred while activating echo: {str(e)}",
                color=0xE02B2B
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="offline",
        description="Deactivate the echo bot in the current channel"
    )
    async def echo_offline(self, interaction: discord.Interaction) -> None:
        """
        Deactivate the echo bot in the current channel.
        
        :param interaction: The application command interaction
        """
        await interaction.response.defer()
        
        try:
            # Check if any echo is active in this channel
            active_echo = await self.session_manager.get_active_echo(interaction.channel.id)
            if not active_echo:
                embed = discord.Embed(
                    title="No Active Echo",
                    description="No echo is currently active in this channel.",
                    color=0xE02B2B
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Stop the echo session
            await self.session_manager.stop_echo_session(
                channel_id=interaction.channel.id,
                requester_id=interaction.user.id
            )
            
            embed = discord.Embed(
                title="Echo Deactivated",
                description=f"Echo for <@{active_echo['user_id']}> has been deactivated in this channel.",
                color=0x9C84EF
            )
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred while deactivating echo: {str(e)}",
                color=0xE02B2B
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="status",
        description="Show the status of echo profiles and active sessions"
    )
    async def echo_status(self, interaction: discord.Interaction) -> None:
        """
        Show the status of echo profiles and active sessions.
        
        :param interaction: The application command interaction
        """
        await interaction.response.defer()
        
        try:
            # Get server statistics
            stats = await self.session_manager.get_server_stats(interaction.guild.id)
            
            embed = discord.Embed(
                title="Echo Status",
                color=0x9C84EF
            )
            
            embed.add_field(
                name="Echo Profiles",
                value=f"Total: {stats['total_profiles']}\nReady: {stats['ready_profiles']}\nTraining: {stats['training_profiles']}",
                inline=True
            )
            
            embed.add_field(
                name="Active Sessions",
                value=f"Current: {stats['active_sessions']}\nMax Allowed: {stats['max_sessions']}",
                inline=True
            )
            
            if stats['active_sessions'] > 0:
                embed.add_field(
                    name="Active Echoes",
                    value="\n".join([f"<@{echo['user_id']}> in <#{echo['channel_id']}>" for echo in stats['active_echoes']]),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred while fetching status: {str(e)}",
                color=0xE02B2B
            )
            await interaction.followup.send(embed=embed)


    async def _can_analyze_user(self, interaction: discord.Interaction, target_user: discord.Member) -> bool:
        """
        Check if the user has permission to analyze the target user.
        
        :param interaction: The interaction object
        :param target_user: The user to be analyzed
        :return: True if analysis is allowed, False otherwise
        """
        # Allow self-analysis
        if interaction.user.id == target_user.id:
            return True
        
        # Allow server administrators
        if interaction.user.guild_permissions.administrator:
            return True
        
        # Allow users with manage_messages permission
        if interaction.user.guild_permissions.manage_messages:
            return True
        
        # TODO: Add more permission checks as needed
        return False


async def setup(bot) -> None:
    await bot.add_cog(Echo(bot))