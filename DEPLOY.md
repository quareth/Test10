# Deployment Guide

This guide covers deploying the Sitemap Scraper application using Docker.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10 or later)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0 or later, or the `docker-compose` plugin)

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd <repository-directory>

# Start the application
docker-compose up --build -d
```

The application will be available at `http://localhost:8000`.

## Environment Variables

Configure these variables in a `.env` file in the project root, or pass them directly to `docker-compose`.

| Variable | Description | Default | Required |
|---|---|---|---|
| `SECRET_KEY` | Secret key used for signing session tokens. **Must be changed in production.** | `change-me-in-production` | Yes (change default) |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins. | `*` (via docker-compose) | Yes (restrict in production) |
| `DATA_DIR` | Directory inside the container where the database and scraped data are stored. | `/app/data` | No |
| `DATABASE_URL` | SQLAlchemy async database URL. | `sqlite+aiosqlite:////app/data/scraper.db` | No |
| `SESSION_EXPIRY_HOURS` | Number of hours before a user session expires. | `24` | No |

Example `.env` file:

```env
SECRET_KEY=your-secure-random-secret-key
ALLOWED_ORIGINS=https://your-domain.com
SESSION_EXPIRY_HOURS=48
```

## Creating the Initial User

After the application is running, create an admin user:

```bash
docker-compose exec app python -m backend.cli create-user admin <password>
```

Replace `<password>` with a strong password. You can then log in through the web interface at `http://localhost:8000`.

To create additional users, run the same command with a different username:

```bash
docker-compose exec app python -m backend.cli create-user <username> <password>
```

## Data Backup

All persistent data is stored in the `data/` directory, which is mounted as a Docker volume from `./data` on the host to `/app/data` in the container. This directory contains:

- `scraper.db` -- the SQLite database (users, targets, scrape jobs, schedules)
- Scraped content files (Markdown output from scrape jobs)

To back up your data:

```bash
# Stop the application first to ensure database consistency
docker-compose stop

# Copy the data directory
cp -r ./data ./data-backup-$(date +%Y%m%d)

# Restart the application
docker-compose start
```

For automated backups, you can also back up while the application is running, though stopping first is recommended for SQLite consistency.

## Updating

To update to a new version:

```bash
# Pull the latest code
git pull

# Rebuild and restart the containers
docker-compose up --build -d
```

The application handles database migrations automatically on startup. Existing data in the `data/` directory is preserved across updates.

## Troubleshooting

### Port conflict on 8000

If port 8000 is already in use, you will see an error like:

```
Error: Bind for 0.0.0.0:8000 failed: port is already allocated
```

Either stop the process using port 8000, or change the host port in `docker-compose.yml`:

```yaml
ports:
  - "9000:8000"  # Maps host port 9000 to container port 8000
```

### Permission errors on the data volume

If you see permission errors related to the `data/` directory:

```bash
# Ensure the data directory exists and is writable
mkdir -p ./data
chmod 755 ./data
```

On Linux, you may need to adjust ownership if the container runs as a different user:

```bash
sudo chown -R 1000:1000 ./data
```

### Container fails to start

Check the container logs for error details:

```bash
docker-compose logs app
```

Common causes:
- Missing or invalid environment variables
- Corrupt database file (restore from backup)
- Out-of-disk space on the host

### Database locked errors

SQLite may report "database is locked" under heavy concurrent use. This is a limitation of SQLite. For production deployments with high traffic, consider switching to PostgreSQL by changing the `DATABASE_URL` environment variable.

## Security Notes

1. **Change the SECRET_KEY**: The default value `change-me-in-production` is insecure. Generate a strong random key:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Restrict ALLOWED_ORIGINS**: The docker-compose default is `*` (all origins). In production, set this to your specific domain:

   ```env
   ALLOWED_ORIGINS=https://your-domain.com
   ```

3. **Use HTTPS via a reverse proxy**: The application serves HTTP on port 8000. Place it behind a reverse proxy (such as Nginx or Caddy) that terminates TLS:

   ```
   Internet -> HTTPS (Nginx/Caddy) -> HTTP (localhost:8000) -> App
   ```

   Example minimal Nginx configuration:

   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

4. **Keep Docker updated**: Regularly update Docker and your base images to receive security patches.

5. **Limit network exposure**: If the application is only accessed through a reverse proxy, bind the Docker port to localhost only:

   ```yaml
   ports:
     - "127.0.0.1:8000:8000"
   ```
