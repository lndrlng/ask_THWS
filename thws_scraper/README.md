# THWS Scraper Project

A Scrapy-based web scraper for THWS websites, with data storage in MongoDB.

## Setup

1. **Create `.env` File:**

   This project uses a `.env` file to manage sensitive configurations like database credentials. Create a file named `.env` in the project's root directory with the following content, replacing placeholder values with your actual credentials:

   ```env
   # .env
   MONGO_USER=scraper
   MONGO_PASS=password
   MONGO_DB=askthws_scraper
   ```

## Running the Scraper

1. **Build and Start Services:**

   Open a terminal in the project's root directory and run:

   ```bash
   docker-compose up -d --build
   ```

1. **Access Services:**

   - **Scraper Logs:** View scraper logs:

     ```bash
     docker-compose logs -f scraper
     ```

   - **Mongo Express (Database Admin UI):**

     Access Mongo Express in your browser at `http://localhost:8081`.

   - **Live Scraper Stats:**

     View live stats from the scraper at `http://localhost:7000/live`.

## Exporting Data from MongoDB

The project includes a script to export the scraper's database (`askthws_scraper`) from the MongoDB container.

1. **Run the export script:**

   The script automatically loads credentials from your `.env` file.

   ```bash
   ./dump_mongo.sh
   ```

   This will create a gzipped archive file in the current directory, named like `askthws_scraper_backup_YYYYMMDD_HHMMSS.gz`. This backup contains the `pages` and `files` collections, including files stored in GridFS.

## Importing (Restoring) Data into MongoDB

You can restore a previously exported database backup into the MongoDB container.

1. **Run the Restore Command:**

   Replace `<BACKUP_FILE_NAME.gz>` with the actual name of your backup file. The `mongodb` is the service name/container name defined in `docker-compose.yml`.
   The `--drop` flag will clear existing collections in the target database before restoring, effectively replacing the content. Remove `--drop` if you want to merge without deleting (be cautious with existing data).

   ```bash
   docker exec -i mongodb mongorestore \
       --username scraper \
       --password password \
       --authenticationDatabase "admin" \
       --archive \
       --gzip \
       --drop < ./<BACKUP_FILE_NAME.gz>
   ```

   This command streams the backup file into the `mongorestore` command running inside the `mongodb` container. The database will be restored under its original name (`askthws_scraper`).
   