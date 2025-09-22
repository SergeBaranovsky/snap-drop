# General deployment steps
docker-compose down
git pull origin main
docker-compose build
docker-compose up -d
# Health checks, etc.