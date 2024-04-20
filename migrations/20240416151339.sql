-- Rename "lost_sector_post_settings" table
RENAME TABLE `lost_sector_post_settings` TO `auto_post_settings`;
ALTER TABLE `auto_post_settings` DROP COLUMN `id`, DROP COLUMN `discord_autopost_enabled`, ADD COLUMN `auto_post_name` varchar(32) NOT NULL, ADD COLUMN `enabled` bool NULL, DROP PRIMARY KEY, ADD PRIMARY KEY (`auto_post_name`);
