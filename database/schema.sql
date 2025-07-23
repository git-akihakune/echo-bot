CREATE TABLE IF NOT EXISTS `warns` (
  `id` int(11) NOT NULL,
  `user_id` varchar(20) NOT NULL,
  `server_id` varchar(20) NOT NULL,
  `moderator_id` varchar(20) NOT NULL,
  `reason` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Echo bot tables
CREATE TABLE IF NOT EXISTS `user_messages` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `user_id` VARCHAR(20) NOT NULL,
  `server_id` VARCHAR(20) NOT NULL,
  `channel_id` VARCHAR(20) NOT NULL,
  `message_content` TEXT NOT NULL,
  `timestamp` DATETIME NOT NULL,
  `message_id` VARCHAR(20) NOT NULL,
  `is_processed` BOOLEAN DEFAULT FALSE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `echo_profiles` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `user_id` VARCHAR(20) NOT NULL,
  `server_id` VARCHAR(20) NOT NULL,
  `cutoff_date` DATE NOT NULL,
  `model_path` VARCHAR(255),
  `training_status` VARCHAR(50) DEFAULT 'not_started',
  `training_progress` INTEGER DEFAULT 0,
  `total_messages` INTEGER DEFAULT 0,
  `processed_messages` INTEGER DEFAULT 0,
  `requester_id` VARCHAR(20) NOT NULL,
  `started_at` TIMESTAMP,
  `completed_at` TIMESTAMP,
  `error_message` TEXT,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `last_updated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(`user_id`, `server_id`)
);

CREATE TABLE IF NOT EXISTS `echo_sessions` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `profile_id` INTEGER NOT NULL,
  `channel_id` VARCHAR(20) NOT NULL,
  `server_id` VARCHAR(20) NOT NULL,
  `is_active` BOOLEAN DEFAULT TRUE,
  `requester_id` VARCHAR(20) NOT NULL,
  `messages_generated` INTEGER DEFAULT 0,
  `conversations_started` INTEGER DEFAULT 0,
  `started_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `stopped_at` TIMESTAMP,
  `last_activity` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`profile_id`) REFERENCES `echo_profiles`(`id`) ON DELETE CASCADE,
  UNIQUE(`channel_id`, `is_active`) WHERE `is_active` = TRUE
);

CREATE TABLE IF NOT EXISTS `echo_responses` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `session_id` INTEGER NOT NULL,
  `response_content` TEXT NOT NULL,
  `context_messages` TEXT,
  `generation_time_ms` INTEGER,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`session_id`) REFERENCES `echo_sessions`(`id`) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS `idx_user_messages_user_server` ON `user_messages`(`user_id`, `server_id`);
CREATE INDEX IF NOT EXISTS `idx_user_messages_timestamp` ON `user_messages`(`timestamp`);
CREATE INDEX IF NOT EXISTS `idx_echo_profiles_user_server` ON `echo_profiles`(`user_id`, `server_id`);
CREATE INDEX IF NOT EXISTS `idx_echo_sessions_channel_active` ON `echo_sessions`(`channel_id`, `is_active`);
CREATE INDEX IF NOT EXISTS `idx_echo_sessions_profile` ON `echo_sessions`(`profile_id`);