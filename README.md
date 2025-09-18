# snap-share
A self-hosted, containerized web application designed to allow event attendees to easily share photos and videos without requiring account creation. 

# Snap-Share

A self-hosted photo and video upload service for event attendees.

## Features

- 🚫 No signup required - just name/email attribution
- 📤 Multiple file upload with drag & drop
- 💾 Local disk or S3 storage options
- 👨‍💼 Admin panel with file management
- 📱 Mobile-friendly responsive design
- 🐳 Docker containerized deployment
- 🔒 HTTPS ready with reverse proxy support

## Quick Start

### 1. Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/SergeBaranovsky/snap-share.git
cd snap-share

# Copy environment template
cp .env.example .env

# Edit .env and set your admin password
nano .env

# Run setup script
chmod +x setup.sh
./setup.sh

# Open in VS Code
code .
```

### 2. Configure Environment

**Important: Change the admin password immediately!**

Edit `.env` file:
```bash
ADMIN_PASSWORD=your-secure-password-here
```

For production, also set via environment variable:
```bash
export ADMIN_PASSWORD="your-secure-password"
```

### 3. Development

#### Local Development
```bash
# Activate virtual environment
source .venv/bin/activate

# Run Flask development server
python app.py
```

Access at: http://localhost:5500

#### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

Access at: http://localhost:8080

### 4. VS Code Integration

The project includes VS Code configuration for:
- **Debug configurations**: Flask development and production modes
- **Tasks**: Setup, install dependencies, run Flask, Docker commands
- **Settings**: Python interpreter, linting, formatting
- **Extensions**: Python, Docker support

#### Available Tasks (Ctrl+Shift+P > "Tasks: Run Task")
- Setup Virtual Environment
- Install Dependencies
- Run Flask Development
- Docker: Build Image
- Docker: Run Container
- Docker Compose: Up/Down/Logs

#### Debug Configurations (F5)
- Flask Development (with debug mode)
- Flask Production Mode
- Docker: Attach to Container

## Configuration

### Environment Variables

Create `.env` file or set in docker-compose.yml:

```bash
# Admin Configuration
ADMIN_PASSWORD=your-secure-password

# S3 Configuration (Optional)
USE_S3=true
S3_BUCKET=your-bucket-name
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

### File Limits

- Max file size: 3GB per file
- Supported formats: JPG, PNG, GIF, WEBP, BMP, TIFF, MP4, AVI, MOV, WMV, FLV, WEBM, MKV, 3GP
- Storage capacity: Configure based on available disk space or S3 limits

## Deployment

### Production Deployment

1. **Setup HTTPS with Nginx Reverse Proxy**:
   ```bash
   # Install nginx and certbot
   sudo apt install nginx certbot python3-certbot-nginx
   
   # Configure subdomain (see deployment guide)
   sudo nano /etc/nginx/sites-available/snap-drop-upload
   
   # Get SSL certificate
   sudo certbot --nginx -d upload.yourdomain.com
   ```

2. **Deploy with Docker Compose**:
   ```bash
   # On your Ubuntu VM
   git clone <your-repo>
   cd snap-drop-upload
   
   # Set production environment variables
   nano docker-compose.yml
   
   # Deploy
   docker-compose up -d
   ```

### Security Notes

- Change default admin password immediately
- Consider adding rate limiting for production
- Files are publicly accessible once uploaded
- Admin panel is password-protected but uses simple authentication

## Project Structure

```
snap-share/
├── .vscode/                 # VS Code configuration
│   ├── launch.json         # Debug configurations
│   ├── settings.json       # Editor settings
│   └── tasks.json          # Build tasks
├── templates/              # Jinja2 templates
│   ├── upload.html         # User upload interface
│   ├── admin_dashboard.html # Admin file management
│   └── admin_login.html    # Admin authentication
├── static/                 # Static assets (future use)
├── uploads/               # Local file storage
├── data/                  # Metadata storage
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── requirements-dev.txt   # Development dependencies
├── Dockerfile            # Container definition
├── docker-compose.yml    # Multi-container setup
├── nginx.conf           # Web server configuration
├── supervisord.conf     # Process management
├── .env                 # Environment variables (not in repo)
├── .env.example         # Environment template
├── .gitignore          # Git ignore rules
├── setup.sh            # Development setup script
└── README.md           # This file
```

## Support

For issues or questions:
1. Check the logs: `docker-compose logs -f`
2. Verify file permissions in uploads directory
3. Check nginx configuration for HTTPS setup
4. Ensure environment variables are set correctly

## License

This project is created for event photo/video sharing and is open source.