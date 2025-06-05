#!/usr/bin/env bash

set -euo pipefail

DB_NAME="askthws_scraper"
MONGO_CONTAINER_NAME="mongodb"
ENV_FILE=".env"

source $ENV_FILE

if [ -z "${MONGO_USER}" ]; then
  echo "ERROR: MONGO_USER is not set. Please define it in '$ENV_FILE' or as an environment variable."
  exit 1
fi
if [ -z "${MONGO_PASS}" ]; then
  echo "ERROR: MONGO_PASS is not set. Please define it in '$ENV_FILE' or as an environment variable."
  exit 1
fi
echo "INFO: Using credentials from '$ENV_FILE'."

# --- Script Logic ---
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE_NAME="${DB_NAME}_backup_${TIMESTAMP}.gz"
BACKUP_PATH_IN_CONTAINER="/tmp/${OUTPUT_FILE_NAME}"

echo "Starting MongoDB dump for database '$DB_NAME' from container '$MONGO_CONTAINER_NAME'..."

docker exec "$MONGO_CONTAINER_NAME" mongodump \
  --username "$MONGO_USER" \
  --password "$MONGO_PASS" \
  --authenticationDatabase "admin" \
  --db "$DB_NAME" \
  --archive="$BACKUP_PATH_IN_CONTAINER" \
  --gzip

if [ $? -ne 0 ]; then
  echo "ERROR: mongodump command failed inside the container '$MONGO_CONTAINER_NAME'."
  exit 1
else
  echo "INFO: Successfully created dump archive at '$BACKUP_PATH_IN_CONTAINER' inside the container."
fi

echo "Copying dump file to host: ./${OUTPUT_FILE_NAME}"
docker cp "${MONGO_CONTAINER_NAME}:${BACKUP_PATH_IN_CONTAINER}" "./${OUTPUT_FILE_NAME}"

if [ $? -ne 0 ]; then
  echo "ERROR: Failed to copy dump file from container to host."
  docker exec "$MONGO_CONTAINER_NAME" rm "$BACKUP_PATH_IN_CONTAINER" >/dev/null 2>&1
  exit 1
else
  echo "INFO: Successfully copied dump file to ./$OUTPUT_FILE_NAME on the host."
fi

echo "Cleaning up temporary archive from container..."
docker exec "$MONGO_CONTAINER_NAME" rm "$BACKUP_PATH_IN_CONTAINER"

if [ $? -ne 0 ]; then
  echo "WARNING: Failed to clean up temporary archive '$BACKUP_PATH_IN_CONTAINER' from inside the container."
else
  echo "INFO: Successfully cleaned up temporary archive from container."
fi

exit 0
