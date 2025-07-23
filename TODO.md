# TODO.md - Echo Bot Implementation

This document outlines the missing core functionality needed to implement the "Echo" bot as described in the README.md.

## Core Echo Functionality (Not Yet Implemented)

### 1. Echo Commands (`/echo` slash command group)

**Missing Implementation:**
- `/echo @user dd.mm.yyyy` - Analyze user messages before cutoff date
- `/echo online` - Activate echo bot in current channel
- `/echo offline` - Deactivate echo bot in current channel

**Implementation Details:**
- Create new cog `cogs/echo.py` with slash command group
- Implement date parsing for `dd.mm.yyyy` format
- Add user mention parsing and validation
- Create channel state management for online/offline status

### 2. Message Data Collection & Storage

**Missing Implementation:**
- Historical message scraping from Discord channels
- Message filtering by user and date cutoff
- Secure local storage of collected messages
- Data preprocessing for LLM training

**Implementation Details:**
- Add database schema for storing user messages:
  ```sql
  CREATE TABLE user_messages (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(20),
    server_id VARCHAR(20),
    channel_id VARCHAR(20),
    message_content TEXT,
    timestamp DATETIME,
    message_id VARCHAR(20)
  );
  ```
- Implement message history fetching using Discord API
- Add data cleaning and tokenization utilities
- Create secure file storage for processed datasets

### 3. Ollama Integration

**Missing Implementation:**
- Ollama client integration for local LLM operations
- Model fine-tuning pipeline
- Model management (loading, unloading, switching)
- Error handling for Ollama service connectivity

**Implementation Details:**
- Add `ollama-python` to requirements.txt
- Create `services/ollama_client.py` for LLM operations
- Implement model fine-tuning workflow:
  - Dataset preparation in Ollama format
  - Model fine-tuning execution
  - Model validation and testing
- Add model state management

### 4. Echo Bot Personality System

**Missing Implementation:**
- User personality profile creation
- Context-aware response generation
- Message pacing and timing simulation
- Conversation initiation logic

**Implementation Details:**
- Create `services/personality_engine.py`
- Implement user writing style analysis
- Add conversation context management
- Create natural message timing algorithms
- Implement proactive conversation starters

### 5. Database Extensions

**Missing Implementation:**
- User echo profiles storage
- Active echo sessions tracking
- Message generation history
- Model training status tracking

**Implementation Details:**
- Extend database schema:
  ```sql
  CREATE TABLE echo_profiles (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(20),
    server_id VARCHAR(20),
    cutoff_date DATE,
    model_path VARCHAR(255),
    training_status VARCHAR(50),
    created_at TIMESTAMP
  );
  
  CREATE TABLE echo_sessions (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER,
    channel_id VARCHAR(20),
    is_active BOOLEAN,
    started_at TIMESTAMP,
    FOREIGN KEY (profile_id) REFERENCES echo_profiles(id)
  );
  ```

### 6. Background Tasks & Processing

**Missing Implementation:**
- Asynchronous message processing
- Model training job queue
- Periodic model updates
- Session cleanup and management

**Implementation Details:**
- Create `services/background_tasks.py`
- Implement asyncio task management
- Add job queue for long-running operations
- Create cleanup routines for expired sessions

### 7. Configuration & Settings

**Missing Implementation:**
- Echo-specific configuration options
- Model parameters and training settings
- Rate limiting and usage controls
- Privacy and data retention policies

**Implementation Details:**
- Extend `config.json` with echo settings:
  ```json
  {
    "echo": {
      "max_messages_per_analysis": 10000,
      "model_training_timeout": 3600,
      "max_active_sessions_per_server": 5,
      "message_generation_cooldown": 2.0,
      "data_retention_days": 30
    }
  }
  ```

### 8. Error Handling & Logging

**Missing Implementation:**
- Echo-specific error handling
- Training progress logging
- Model performance monitoring
- User feedback collection

**Implementation Details:**
- Add echo-specific log levels and formatting
- Implement training progress tracking
- Create error recovery mechanisms
- Add user notification system for failures

### 9. Security & Privacy

**Missing Implementation:**
- Message data encryption at rest
- User consent management
- Data deletion capabilities
- Access control for echo profiles

**Implementation Details:**
- Implement message encryption before storage
- Add user consent tracking system
- Create data deletion utilities
- Implement profile access controls

### 10. Performance Optimization

**Missing Implementation:**
- Message processing optimization
- Model loading/unloading strategies
- Resource usage monitoring
- Concurrent session management

**Implementation Details:**
- Add async processing for large datasets
- Implement model caching strategies
- Create resource monitoring utilities
- Add concurrent session limits

## File Structure Extensions Needed

```
cogs/
├── echo.py                    # Main echo commands
services/
├── __init__.py
├── ollama_client.py          # Ollama integration
├── personality_engine.py     # AI personality system
├── message_processor.py      # Message data processing
├── background_tasks.py       # Async task management
└── security.py              # Data encryption/privacy
utils/
├── __init__.py
├── date_parser.py           # Date parsing utilities
├── text_processor.py        # Text cleaning/tokenization
└── validation.py            # Input validation
```

## Dependencies to Add

```txt
ollama-python>=0.3.0
cryptography>=41.0.0
aiofiles>=23.0.0
python-dateutil>=2.8.0
```

## Testing Requirements

- Unit tests for all new services
- Integration tests for Ollama communication
- Discord API interaction tests
- Database operation tests
- End-to-end echo workflow tests

## Documentation Needed

- API documentation for new services
- User guide for echo functionality
- Privacy policy for data handling
- Troubleshooting guide for common issues