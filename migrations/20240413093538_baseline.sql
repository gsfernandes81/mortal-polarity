-- Create "lost_sector_post_settings" table
CREATE TABLE `lost_sector_post_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `discord_autopost_enabled` bool NULL,
  `twitter_autopost_enabled` bool NULL,
  PRIMARY KEY (`id`)
) CHARSET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
