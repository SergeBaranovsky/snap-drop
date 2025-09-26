from flask import (
    Flask,
    request,
    render_template,
    jsonify,
    send_file,
    abort,
    redirect,
    url_for,
    session,
)
import os
import json
import uuid
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import mimetypes
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024 * 1024  # 3GB max file size

# Session configuration for admin authentication
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    secret_key = "change-me-in-production-" + str(uuid.uuid4())
    logger.warning(
        "Using auto-generated SECRET_KEY - sessions will not persist across restarts!"
    )

app.secret_key = secret_key
use_https = os.environ.get("USE_HTTPS", "false").lower() == "true"
app.config["SESSION_COOKIE_SECURE"] = use_https
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 3600  # 1 hour timeout

logger.info(
    f"Session config - USE_HTTPS: {use_https}, COOKIE_SECURE: {app.config['SESSION_COOKIE_SECURE']}"
)

# Configuration
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "./uploads")
METADATA_FILE = os.path.join(UPLOAD_FOLDER, "metadata.json")
ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "bmp",
    "tiff",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "flv",
    "webm",
    "mkv",
    "3gp",
}

# S3 Configuration (optional)
USE_S3 = os.environ.get("USE_S3", "false").lower() == "true"
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

# Admin password
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

# Debug logging for S3 configuration
logger.info("=== S3 Configuration Debug ===")
logger.info(f"USE_S3 env var: '{os.environ.get('USE_S3', 'NOT_SET')}'")
logger.info(f"USE_S3 parsed: {USE_S3}")
logger.info(f"S3_BUCKET: '{S3_BUCKET}' (empty: {not S3_BUCKET})")
logger.info(f"S3_REGION: '{S3_REGION}'")
logger.info(f"AWS_ACCESS_KEY_ID: {'SET' if AWS_ACCESS_KEY else 'NOT_SET'}")
logger.info(f"AWS_SECRET_ACCESS_KEY: {'SET' if AWS_SECRET_KEY else 'NOT_SET'}")

if USE_S3 and S3_BUCKET:
    logger.info("✅ S3 client initialization: SUCCESS")
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
    )
else:
    logger.warning(
        "❌ S3 client initialization: FAILED - falling back to local storage"
    )
    logger.warning(f"   Reason: USE_S3={USE_S3}, S3_BUCKET_EMPTY={not S3_BUCKET}")
    s3_client = None
    USE_S3 = False

logger.info(f"Final storage mode: {'S3' if USE_S3 else 'LOCAL'}")
logger.info("=== End S3 Configuration Debug ===")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def require_admin_session(f):
    """Decorator to require admin session for protected routes"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_authenticated = session.get("admin_authenticated")
        logger.info(
            f"Auth check for {request.endpoint}: authenticated={is_authenticated}, session_id={session.get('_id', 'none')}"
        )

        if not is_authenticated:
            logger.warning(
                f"Unauthenticated access to {request.endpoint}, redirecting to login"
            )
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return decorated_function


def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return []


def save_metadata(metadata):
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_type(filename):
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff"}:
        return "image"
    elif ext in {"mp4", "avi", "mov", "wmv", "flv", "webm", "mkv", "3gp"}:
        return "video"
    return "unknown"


def sanitize_folder_name(name):
    """Sanitize name for filesystem compatibility"""
    # Use secure_filename to handle most cases, then replace spaces with hyphens
    sanitized = secure_filename(name)
    # Replace spaces and underscores with hyphens for consistency
    sanitized = sanitized.replace(" ", "-").replace("_", "-")
    # Remove any double hyphens
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip("-")
    # Ensure we have something left, fallback to 'user' if empty
    return sanitized if sanitized else "user"


def generate_upload_folder(uploader_name, upload_time):
    """Generate sanitized folder name from uploader name and timestamp"""
    # Sanitize the uploader name
    clean_name = sanitize_folder_name(uploader_name)

    # Format timestamp as YYYYMMDD-HHMMSS
    if isinstance(upload_time, str):
        # Parse ISO format timestamp
        upload_time = datetime.fromisoformat(upload_time.replace("Z", "+00:00"))

    timestamp_str = upload_time.strftime("%Y%m%d-%H%M%S")

    # Combine name and timestamp
    folder_name = f"{clean_name}-{timestamp_str}"

    return folder_name


def ensure_upload_directory(folder_path):
    """Create directory if it doesn't exist"""
    full_path = os.path.join(UPLOAD_FOLDER, folder_path)
    os.makedirs(full_path, exist_ok=True)
    return full_path


def upload_to_s3(file_path, s3_key):
    if not USE_S3:
        logger.warning(f"S3 upload skipped - USE_S3 is False")
        return False

    logger.info(f"🔄 Attempting S3 upload: {s3_key}")
    logger.info(f"   Local file: {file_path}")
    logger.info(f"   S3 bucket: {S3_BUCKET}")
    logger.info(f"   S3 region: {S3_REGION}")

    try:
        s3_client.upload_file(file_path, S3_BUCKET, s3_key)
        logger.info(f"✅ S3 upload SUCCESS: {s3_key}")
        return True
    except ClientError as e:
        logger.error(f"❌ S3 upload FAILED: {s3_key}")
        logger.error(f"   Error code: {e.response['Error']['Code']}")
        logger.error(f"   Error message: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        logger.error(f"❌ S3 upload FAILED with unexpected error: {s3_key}")
        logger.error(f"   Error: {str(e)}")
        return False


@app.route("/")
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload_files():
    if "files" not in request.files:
        return jsonify({"error": "No files selected"}), 400

    files = request.files.getlist("files")
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400

    uploaded_files = []
    metadata = load_metadata()

    # Generate upload folder for this batch of files
    upload_time = datetime.now()
    folder_path = generate_upload_folder(name, upload_time)

    # Create the upload directory
    upload_dir = ensure_upload_directory(folder_path)

    for file in files:
        if file and file.filename and allowed_file(file.filename):
            # Generate unique filename
            file_id = str(uuid.uuid4())
            original_filename = secure_filename(file.filename)
            ext = original_filename.rsplit(".", 1)[1].lower()
            stored_filename = f"{file_id}.{ext}"

            # Save to organized folder structure
            file_path = os.path.join(upload_dir, stored_filename)
            file.save(file_path)

            # Upload to S3 if configured (with organized path)
            s3_url = None
            if USE_S3:
                s3_key = f"snap-drop-uploads/{folder_path}/{stored_filename}"
                if upload_to_s3(file_path, s3_key):
                    s3_url = (
                        f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"
                    )
                    # Remove local file if S3 upload successful
                    os.remove(file_path)

            # Add to metadata with new folder structure
            file_metadata = {
                "id": file_id,
                "original_name": original_filename,
                "stored_name": stored_filename,
                "folder_path": folder_path,
                "full_path": f"{folder_path}/{stored_filename}",
                "upload_time": upload_time.isoformat(),
                "uploader_name": name,
                "uploader_email": email,
                "file_type": get_file_type(original_filename),
                "file_size": os.path.getsize(file_path) if not USE_S3 else None,
                "s3_url": s3_url,
            }

            metadata.append(file_metadata)
            uploaded_files.append(original_filename)

    if uploaded_files:
        save_metadata(metadata)
        return jsonify(
            {
                "message": f"Successfully uploaded {len(uploaded_files)} files",
                "files": uploaded_files,
            }
        )
    else:
        return (
            jsonify(
                {
                    "error": "No valid files uploaded. Allowed: "
                    + ", ".join(ALLOWED_EXTENSIONS)
                }
            ),
            400,
        )


@app.route("/admin")
def admin_login():
    # Check if admin is already authenticated
    if session.get("admin_authenticated"):
        logger.info(
            f"Already authenticated admin accessing /admin, redirecting to dashboard"
        )
        return redirect(url_for("admin_dashboard"))

    # Show login form for unauthenticated users
    return render_template("admin_login.html")


@app.route("/admin/login", methods=["POST"])
def admin_login_handler():
    password = request.form.get("password")
    logger.info(f"Login attempt from {request.remote_addr}")

    if password == ADMIN_PASSWORD:
        session["admin_authenticated"] = True
        session.permanent = True
        session_id = session.get("_id", "generated")
        logger.info(
            f"Successful login, session_id={session_id}, cookie_secure={app.config['SESSION_COOKIE_SECURE']}"
        )
        return redirect(url_for("admin_dashboard"))
    else:
        logger.warning(f"Failed login attempt from {request.remote_addr}")
        return redirect(url_for("admin_login") + "?error=1")


@app.route("/admin/dashboard")
@require_admin_session
def admin_dashboard():
    metadata = load_metadata()
    # Sort by upload time, newest first
    metadata.sort(key=lambda x: x["upload_time"], reverse=True)

    return render_template("admin_dashboard.html", files=metadata)


@app.route("/admin/logout", methods=["POST"])
@require_admin_session
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/delete/<file_id>", methods=["POST"])
@require_admin_session
def delete_file(file_id):

    metadata = load_metadata()
    file_to_delete = None

    for i, file_meta in enumerate(metadata):
        if file_meta["id"] == file_id:
            file_to_delete = metadata.pop(i)
            break

    if file_to_delete:
        # Delete from S3 if applicable
        if USE_S3 and file_to_delete.get("s3_url"):
            # Use new folder structure for S3 key if available
            if file_to_delete.get("folder_path"):
                s3_key = f"snap-drop-uploads/{file_to_delete['folder_path']}/{file_to_delete['stored_name']}"
            else:
                # Backward compatibility for old files
                s3_key = f"snap-drop-uploads/{file_to_delete['stored_name']}"
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
            except ClientError:
                pass

        # Delete local file if it exists
        if file_to_delete.get("folder_path"):
            # New folder structure
            local_path = os.path.join(
                UPLOAD_FOLDER,
                file_to_delete["folder_path"],
                file_to_delete["stored_name"],
            )
        else:
            # Backward compatibility for old files
            local_path = os.path.join(UPLOAD_FOLDER, file_to_delete["stored_name"])

        if os.path.exists(local_path):
            os.remove(local_path)

        save_metadata(metadata)
        return jsonify({"message": "File deleted successfully"})

    return jsonify({"error": "File not found"}), 404


@app.route("/file/<file_id>")
def serve_file(file_id):
    metadata = load_metadata()

    for file_meta in metadata:
        if file_meta["id"] == file_id:
            if USE_S3 and file_meta.get("s3_url"):
                return redirect(file_meta["s3_url"])
            else:
                # Check for new folder structure first
                if file_meta.get("folder_path"):
                    file_path = os.path.join(
                        UPLOAD_FOLDER,
                        file_meta["folder_path"],
                        file_meta["stored_name"],
                    )
                else:
                    # Backward compatibility for old files
                    file_path = os.path.join(UPLOAD_FOLDER, file_meta["stored_name"])

                if os.path.exists(file_path):
                    return send_file(file_path, as_attachment=False)

    abort(404)


@app.route("/thumbnail/<file_id>")
def serve_thumbnail(file_id):
    # For now, just serve the original file. You could add thumbnail generation here.
    return serve_file(file_id)


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({"error": "File too large. Maximum size is 3GB."}), 413


@app.errorhandler(413)
def handle_413(e):
    return jsonify({"error": "File too large. Maximum size is 3GB."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5500, debug=False)
