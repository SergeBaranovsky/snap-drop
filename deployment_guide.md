# Snap-Share Deployment Guide

## Quick Start

1. **Clone repository**:
```bash
git clone https://github.com/yourusername/snap-share.git
cd snap-share
```

2. **Configure environment**:
```bash
cp .env.example .env
nano .env  # Set ADMIN_PASSWORD and other config
```

3. **Build and run**:
```bash
docker-compose up -d
```

4. **Access the service**:
- Upload page: `http://your-server:8080`
- Admin panel: `http://your-server:8080/admin` (use your password from .env)

## HTTPS Setup (Subdomain)

### Option 1: Nginx Reverse Proxy (Recommended)

On your Ubuntu VM, install nginx and certbot:

```bash
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx
```

Create nginx config for subdomain (`/etc/nginx/sites-available/snap-share`):

```nginx
server {
    listen 80;
    server_name upload.yourdomain.com;  # Replace with your subdomain

    client_max_body_size 3G;
    client_body_timeout 300s;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

Enable and get SSL:
```bash
sudo ln -s /etc/nginx/sites-available/snap-share /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d upload.yourdomain.com
```

### Option 2: Traefik (Docker-based)

Update `docker-compose.yml`:

```yaml
version: '3.8'

services:
  snap-share:
    build: .
    expose:
      - "80"
    volumes:
      - ./uploads:/app/uploads
    environment:
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-changeme123}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.snapshare.rule=Host(`upload.yourdomain.com`)"
      - "traefik.http.routers.snapshare.tls.certresolver=letsencrypt"
    restart: unless-stopped

  traefik:
    image: traefik:v2.10
    command:
      - "--api.dashboard=true"
      - "--providers.docker=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=your@email.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./letsencrypt:/letsencrypt
    restart: unless-stopped
```

## Configuration Options

### Environment Variables

- `ADMIN_PASSWORD`: Admin panel password (default: `changeme123`)
- `USE_S3`: Enable S3 storage (`true`/`false`)
- `S3_BUCKET`: S3 bucket name
- `S3_REGION`: S3 region
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key

### S3 Setup (Optional)

1. Create S3 bucket with public read access
2. Set environment variables in docker-compose.yml
3. Files will be stored in S3 instead of local disk

### Security Notes

- Change default admin password immediately
- Consider adding rate limiting for uploads
- The current setup allows anyone to upload - no authentication required
- Admin can view/delete all files
- Files are stored with attribution (name/email) but no verification

### File Limits

- Max file size: 3GB per file
- Supported formats: JPG, PNG, GIF, WEBP, BMP, TIFF, MP4, AVI, MOV, WMV, FLV, WEBM, MKV, 3GP
- No limit on total files uploaded

### Storage Requirements

- Local storage: Files stored in `./uploads` directory
- For 200GB capacity, ensure your host has sufficient disk space
- Consider using S3 for better scalability and backups

## Monitoring & Maintenance

### View logs:
```bash
docker-compose logs -f
```

### Backup uploads:
```bash
tar -czf snap-drop-backup-$(date +%Y%m%d).tar.gz uploads/
```

### Update service:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Features Included

✅ No signup required - just name/email attribution  
✅ Multiple file upload with drag & drop  
✅ Both local and S3 storage options  
✅ Admin panel with file viewing/management  
✅ File type restrictions  
✅ Self-hosted Docker solution  
✅ HTTPS-ready with reverse proxy  
✅ Responsive UI for mobile uploads  
✅ Admin can delete files  
✅ In-browser image/video viewing  
