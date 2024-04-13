-- MySQL dump 10.13  Distrib 8.0.36, for Linux (x86_64)
--
-- Host: monorail.proxy.rlwy.net    Database: railway
-- ------------------------------------------------------
-- Server version	8.3.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `atlas_schema_revisions`
--

DROP TABLE IF EXISTS `atlas_schema_revisions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `atlas_schema_revisions` (
  `version` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `type` bigint unsigned NOT NULL DEFAULT '2',
  `applied` bigint NOT NULL DEFAULT '0',
  `total` bigint NOT NULL DEFAULT '0',
  `executed_at` timestamp NOT NULL,
  `execution_time` bigint NOT NULL,
  `error` longtext COLLATE utf8mb4_bin,
  `error_stmt` longtext COLLATE utf8mb4_bin,
  `hash` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `partial_hashes` json DEFAULT NULL,
  `operator_version` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `atlas_schema_revisions`
--

LOCK TABLES `atlas_schema_revisions` WRITE;
/*!40000 ALTER TABLE `atlas_schema_revisions` DISABLE KEYS */;
INSERT INTO `atlas_schema_revisions` VALUES ('20240413093538','baseline',2,1,1,'2024-04-13 14:10:44',410341502,'','','Bc4/TsoaziksCMuoVZY2kHb1UaSz7PoqAbVIVb9MX+M=','[\"h1:+4xr+ho6j5FlU3TPC2aUwGMnQAUsRvi8saL8oPMoF+E=\"]','Atlas CLI v0.21.2-ae7eac8-canary');
/*!40000 ALTER TABLE `atlas_schema_revisions` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2024-04-13 15:16:32
