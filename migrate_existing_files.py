#!/usr/bin/env python3
"""
Migration script to move existing files to organized folder structure.

This script:
1. Reads existing metadata.json
2. For each file without folder_path, creates appropriate folder structure
3. Moves files from uploads root to organized subfolders
4. Updates metadata with new folder paths
5. Handles both local files and S3 files

Usage: python3 migrate_existing_files.py [--dry-run]
"""

import os
import json
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import argparse

# Load environment variables
load_dotenv()

# Configuration
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "./uploads")
METADATA_FILE = os.path.join(UPLOAD_FOLDER, "metadata.json")
USE_S3 = os.environ.get("USE_S3", "false").lower() == "true"
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

# Initialize S3 client if needed
s3_client = None
if USE_S3 and S3_BUCKET:
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
    )


def sanitize_folder_name(name):
    """Sanitize name for filesystem compatibility"""
    sanitized = secure_filename(name)
    sanitized = sanitized.replace(" ", "-").replace("_", "-")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    sanitized = sanitized.strip("-")
    return sanitized if sanitized else "user"


def generate_upload_folder(uploader_name, upload_time):
    """Generate sanitized folder name from uploader name and timestamp"""
    clean_name = sanitize_folder_name(uploader_name)

    if isinstance(upload_time, str):
        upload_time = datetime.fromisoformat(upload_time.replace("Z", "+00:00"))

    timestamp_str = upload_time.strftime("%Y%m%d-%H%M%S")
    folder_name = f"{clean_name}-{timestamp_str}"

    return folder_name


def load_metadata():
    """Load metadata from JSON file"""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return []


def save_metadata(metadata):
    """Save metadata to JSON file"""
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def backup_metadata():
    """Create backup of metadata file"""
    if os.path.exists(METADATA_FILE):
        backup_file = (
            f"{METADATA_FILE}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(METADATA_FILE, backup_file)
        print(f"✓ Created metadata backup: {backup_file}")
        return backup_file
    return None


def copy_s3_object(old_key, new_key):
    """Copy S3 object to new key and delete old one"""
    if not s3_client:
        return False

    try:
        # Copy object to new location
        copy_source = {"Bucket": S3_BUCKET, "Key": old_key}
        s3_client.copy_object(CopySource=copy_source, Bucket=S3_BUCKET, Key=new_key)

        # Delete old object
        s3_client.delete_object(Bucket=S3_BUCKET, Key=old_key)
        return True
    except ClientError as e:
        print(f"✗ S3 operation failed for {old_key} -> {new_key}: {e}")
        return False


def migrate_files(dry_run=False):
    """Migrate existing files to organized folder structure"""
    print("🔄 Starting file migration to organized folder structure...")

    if dry_run:
        print("🔍 DRY RUN MODE - No files will be moved")

    # Load existing metadata
    metadata = load_metadata()
    if not metadata:
        print("ℹ️  No metadata found - nothing to migrate")
        return

    # PRE-FLIGHT CHECKS - Validate permissions before any file operations
    if not dry_run:
        print("🔍 Validating permissions before migration...")

        # Check metadata file write permissions
        if not os.access(METADATA_FILE, os.W_OK):
            print(f"✗ Cannot write to metadata file: {METADATA_FILE}")
            print(f"💡 Fix with: chmod 644 {METADATA_FILE}")
            return

        # Test write access by attempting to open for append
        try:
            with open(METADATA_FILE, "a"):
                pass
        except PermissionError:
            print(f"✗ No write permission for metadata file: {METADATA_FILE}")
            print(f"💡 Fix with: chmod 644 {METADATA_FILE}")
            return
        except Exception as e:
            print(f"✗ Cannot access metadata file: {e}")
            return

        # Check upload directory write permissions
        if not os.access(UPLOAD_FOLDER, os.W_OK):
            print(f"✗ Cannot write to upload directory: {UPLOAD_FOLDER}")
            print(f"💡 Fix with: chmod 755 {UPLOAD_FOLDER}")
            return

        print("✓ All permission checks passed")

    # Create backup
    if not dry_run:
        backup_metadata()

    files_to_migrate = []
    files_already_organized = []

    # Identify files that need migration
    for file_meta in metadata:
        if file_meta.get("folder_path"):
            files_already_organized.append(file_meta)
        else:
            files_to_migrate.append(file_meta)

    print(f"📊 Found {len(files_already_organized)} already organized files")
    print(f"📊 Found {len(files_to_migrate)} files to migrate")

    if not files_to_migrate:
        print("✅ All files are already organized!")
        return

    migrated_count = 0
    error_count = 0

    for file_meta in files_to_migrate:
        try:
            # Generate folder path for this file
            folder_path = generate_upload_folder(
                file_meta["uploader_name"], file_meta["upload_time"]
            )

            print(f"\n📁 Migrating: {file_meta['original_name']} -> {folder_path}/")

            # Handle local file migration
            old_local_path = os.path.join(UPLOAD_FOLDER, file_meta["stored_name"])
            new_folder_path = os.path.join(UPLOAD_FOLDER, folder_path)
            new_local_path = os.path.join(new_folder_path, file_meta["stored_name"])

            local_file_exists = os.path.exists(old_local_path)
            s3_file_exists = USE_S3 and file_meta.get("s3_url")

            if not local_file_exists and not s3_file_exists:
                print(f"⚠️  File not found in local or S3: {file_meta['stored_name']}")
                error_count += 1
                continue

            if not dry_run:
                # Create new folder structure
                os.makedirs(new_folder_path, exist_ok=True)

                # Move local file if it exists
                if local_file_exists:
                    shutil.move(old_local_path, new_local_path)
                    print(f"✓ Moved local file: {old_local_path} -> {new_local_path}")

                # Handle S3 file migration
                if s3_file_exists:
                    old_s3_key = f"snap-drop-uploads/{file_meta['stored_name']}"
                    new_s3_key = (
                        f"snap-drop-uploads/{folder_path}/{file_meta['stored_name']}"
                    )

                    if copy_s3_object(old_s3_key, new_s3_key):
                        # Update S3 URL
                        file_meta["s3_url"] = (
                            f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{new_s3_key}"
                        )
                        print(f"✓ Moved S3 file: {old_s3_key} -> {new_s3_key}")
                    else:
                        print(f"✗ Failed to move S3 file: {old_s3_key}")
                        error_count += 1
                        continue

                # Update metadata
                file_meta["folder_path"] = folder_path
                file_meta["full_path"] = f"{folder_path}/{file_meta['stored_name']}"

            else:
                print(f"🔍 Would create folder: {new_folder_path}")
                if local_file_exists:
                    print(f"🔍 Would move local: {old_local_path} -> {new_local_path}")
                if s3_file_exists:
                    old_s3_key = f"snap-drop-uploads/{file_meta['stored_name']}"
                    new_s3_key = (
                        f"snap-drop-uploads/{folder_path}/{file_meta['stored_name']}"
                    )
                    print(f"🔍 Would move S3: {old_s3_key} -> {new_s3_key}")

            migrated_count += 1

        except Exception as e:
            print(f"✗ Error migrating {file_meta.get('original_name', 'unknown')}: {e}")
            error_count += 1

    # Save updated metadata
    if not dry_run and migrated_count > 0:
        save_metadata(metadata)
        print(f"\n✅ Updated metadata.json with new folder paths")

    # Summary
    print(f"\n📈 Migration Summary:")
    print(f"   • Files migrated: {migrated_count}")
    print(f"   • Errors: {error_count}")
    print(f"   • Already organized: {len(files_already_organized)}")

    if dry_run:
        print(
            f"\n🔍 This was a dry run. Run without --dry-run to perform actual migration."
        )
    elif migrated_count > 0:
        print(f"\n✅ Migration completed successfully!")
        print(f"   • Metadata backup created")
        print(f"   • Files moved to organized folder structure")
        print(f"   • S3 objects relocated (if applicable)")
    else:
        print(f"\n⚠️  No files were migrated.")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate existing files to organized folder structure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    print("🚀 Snap-Drop File Migration Tool")
    print("=" * 50)

    # Verify configuration
    print(f"📂 Upload folder: {UPLOAD_FOLDER}")
    print(f"📄 Metadata file: {METADATA_FILE}")
    print(f"☁️  S3 enabled: {USE_S3}")
    if USE_S3:
        print(f"🪣 S3 bucket: {S3_BUCKET}")

    if not os.path.exists(UPLOAD_FOLDER):
        print(f"✗ Upload folder does not exist: {UPLOAD_FOLDER}")
        return 1

    if not os.path.exists(METADATA_FILE):
        print(f"✗ Metadata file does not exist: {METADATA_FILE}")
        return 1

    try:
        migrate_files(dry_run=args.dry_run)
        return 0
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
