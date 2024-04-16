-- Create "bungie_credentials" table
CREATE TABLE `bungie_credentials` (
  `id` int NOT NULL AUTO_INCREMENT,
  `refresh_token` varchar(1024) NULL,
  `refresh_token_expires` datetime NULL,
  PRIMARY KEY (`id`)
) CHARSET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
