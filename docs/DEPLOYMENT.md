# Thalamus Deployment Guide

## Prerequisites

### System Requirements
- **Python**: 3.8 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 2GB RAM (4GB+ recommended)
- **Storage**: 1GB+ free space for database and logs
- **Network**: Internet access for OpenAI API

### Required Accounts
- **OpenAI API**: Account with API key and credits

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/thalamus.git
cd thalamus
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

**Note**: SQLite is included with Python and requires no additional setup.

### 4. Environment Configuration
Create `.env` file in project root:
```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional
DATABASE_URL=sqlite:///thalamus.db
LOG_LEVEL=INFO
PROCESSING_TIMEOUT=120
MIN_SEGMENTS_FOR_REFINEMENT=4
```

### 5. Initialize Database
```bash
python init_db.py
```

## Development Setup

### Quick Start
1. **Start Data Ingestion**:
   ```bash
   python thalamus_app.py
   ```

2. **Start Transcript Refiner** (in separate terminal):
   ```bash
   python transcript_refiner.py
   ```

3. **Monitor Processing**:
   ```bash
   # Check database state
   python check_db.py
   
   # Audit data integrity
   python audit_segment_usage.py
   ```

### Development Workflow
1. **Data Preparation**: Place test data in `raw_data_log.json`
2. **Processing**: Run both components simultaneously
3. **Monitoring**: Use audit tools to verify results
4. **Debugging**: Check logs in `transcript_refiner.log`

## Production Deployment

### Single-Server Deployment

#### 1. Server Preparation
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3 python3-pip python3-venv

# SQLite is included with Python - no additional installation needed
```

#### 2. Application Setup
```bash
# Create application directory
sudo mkdir -p /opt/thalamus
sudo chown $USER:$USER /opt/thalamus
cd /opt/thalamus

# Clone repository
git clone https://github.com/yourusername/thalamus.git .

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 3. Configuration
```bash
# Create environment file
cat > .env << EOF
OPENAI_API_KEY=your_production_api_key
DATABASE_URL=sqlite:///thalamus.db
LOG_LEVEL=INFO
PROCESSING_TIMEOUT=120
MIN_SEGMENTS_FOR_REFINEMENT=4
EOF

# Initialize database
python init_db.py
```

#### 4. Service Configuration
Create systemd service files:

**Thalamus App Service** (`/etc/systemd/system/thalamus-app.service`):
```ini
[Unit]
Description=Thalamus Data Ingestion Service
After=network.target

[Service]
Type=simple
User=thalamus
WorkingDirectory=/opt/thalamus
Environment=PATH=/opt/thalamus/venv/bin
ExecStart=/opt/thalamus/venv/bin/python thalamus_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Transcript Refiner Service** (`/etc/systemd/system/thalamus-refiner.service`):
```ini
[Unit]
Description=Thalamus Transcript Refinement Service
After=network.target

[Service]
Type=simple
User=thalamus
WorkingDirectory=/opt/thalamus
Environment=PATH=/opt/thalamus/venv/bin
ExecStart=/opt/thalamus/venv/bin/python transcript_refiner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 5. Start Services
```bash
# Create service user
sudo useradd -r -s /bin/false thalamus
sudo chown -R thalamus:thalamus /opt/thalamus

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable thalamus-app
sudo systemctl enable thalamus-refiner
sudo systemctl start thalamus-app
sudo systemctl start thalamus-refiner

# Check status
sudo systemctl status thalamus-app
sudo systemctl status thalamus-refiner
```

### Multi-Server Deployment

#### Load Balancer Configuration
```nginx
# Nginx configuration
upstream thalamus_backend {
    server 192.168.1.10:5000;
    server 192.168.1.11:5000;
    server 192.168.1.12:5000;
}

server {
    listen 80;
    server_name thalamus.yourdomain.com;

    location / {
        proxy_pass http://thalamus_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Database Configuration
SQLite is used by default and requires no additional configuration. The database file will be created automatically when you run `python init_db.py`.

## Monitoring and Logging

### Log Management
```bash
# Configure log rotation
sudo tee /etc/logrotate.d/thalamus << EOF
/opt/thalamus/transcript_refiner.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 thalamus thalamus
}
EOF
```

### Health Checks
Create health check script (`/opt/thalamus/health_check.py`):
```python
#!/usr/bin/env python3
import sqlite3
import sys
import os

def check_database():
    try:
        conn = sqlite3.connect('thalamus.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sessions')
        count = cursor.fetchone()[0]
        conn.close()
        return count >= 0
    except Exception as e:
        print(f"Database check failed: {e}")
        return False

def check_services():
    # Check if services are running
    import subprocess
    try:
        result = subprocess.run(['systemctl', 'is-active', 'thalamus-app'], 
                              capture_output=True, text=True)
        app_running = result.stdout.strip() == 'active'
        
        result = subprocess.run(['systemctl', 'is-active', 'thalamus-refiner'], 
                              capture_output=True, text=True)
        refiner_running = result.stdout.strip() == 'active'
        
        return app_running and refiner_running
    except Exception as e:
        print(f"Service check failed: {e}")
        return False

if __name__ == '__main__':
    db_ok = check_database()
    services_ok = check_services()
    
    if db_ok and services_ok:
        print("OK")
        sys.exit(0)
    else:
        print("ERROR")
        sys.exit(1)
```

### Monitoring Dashboard
Set up monitoring with Prometheus and Grafana:

**Prometheus Configuration** (`prometheus.yml`):
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'thalamus'
    static_configs:
      - targets: ['localhost:5000']
```

## Backup and Recovery

### Database Backup
```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/opt/backups/thalamus"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# SQLite backup
cp /opt/thalamus/thalamus.db $BACKUP_DIR/thalamus_$DATE.db

# SQLite backup (database file)
cp /opt/thalamus/thalamus.db $BACKUP_DIR/thalamus_$DATE.db

# Keep only last 7 days
find $BACKUP_DIR -name "thalamus_*" -mtime +7 -delete
```

### Recovery Procedures
```bash
# Restore SQLite database
cp /opt/backups/thalamus/thalamus_20250101_120000.db /opt/thalamus/thalamus.db

# Restore SQLite database
cp /opt/backups/thalamus/thalamus_20250101_120000.db /opt/thalamus/thalamus.db
```

## Security Considerations

### API Key Security
```bash
# Secure API key storage
sudo chmod 600 /opt/thalamus/.env
sudo chown thalamus:thalamus /opt/thalamus/.env
```

### Network Security
```bash
# Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Database Security
```bash
# SQLite file permissions
sudo chmod 600 /opt/thalamus/thalamus.db
sudo chown thalamus:thalamus /opt/thalamus/thalamus.db
```

## Performance Tuning

### Database Optimization
```sql
-- Create indexes for better performance
CREATE INDEX idx_raw_segments_session_id ON raw_segments(session_id);
CREATE INDEX idx_raw_segments_timestamp ON raw_segments(timestamp);
CREATE INDEX idx_refined_segments_session_id ON refined_segments(session_id);
CREATE INDEX idx_segment_usage_raw_id ON segment_usage(raw_segment_id);
```

### Application Tuning
```python
# Adjust processing parameters in transcript_refiner.py
class TranscriptRefiner:
    def __init__(self, min_segments_for_diarization=2, inactivity_seconds=60):
        # Reduce minimum segments for faster processing
        # Reduce inactivity timeout for quicker cleanup
```

### System Tuning
```bash
# Increase file descriptor limits
echo "thalamus soft nofile 65536" >> /etc/security/limits.conf
echo "thalamus hard nofile 65536" >> /etc/security/limits.conf

# Optimize kernel parameters
echo "vm.swappiness=10" >> /etc/sysctl.conf
echo "vm.dirty_ratio=15" >> /etc/sysctl.conf
sysctl -p
```

## Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check service status
sudo systemctl status thalamus-app

# View logs
sudo journalctl -u thalamus-app -f

# Check permissions
ls -la /opt/thalamus/
```

#### Database Connection Issues
```bash
# Test database connection
python -c "from database import get_db; print('DB OK')"

# Check database file
ls -la thalamus.db
sqlite3 thalamus.db ".tables"
```

#### OpenAI API Issues
```bash
# Test API connection
python -c "from openai_wrapper import call_openai_text; print(call_openai_text('test'))"

# Check API key
echo $OPENAI_API_KEY
```

#### Performance Issues
```bash
# Monitor system resources
htop
iotop
df -h

# Check database size
ls -lh thalamus.db
```

### Debug Commands
```bash
# Check database state
python check_db.py

# Audit segment integrity
python audit_segment_usage.py

# View processing logs
tail -f transcript_refiner.log

# Monitor system resources
watch -n 1 'ps aux | grep python'
```

## Scaling Considerations

### Horizontal Scaling
- **Load Balancer**: Distribute incoming requests
- **Database Sharding**: Split data by session ID
- **Message Queues**: Use RabbitMQ or Redis for async processing
- **Caching**: Implement Redis for frequently accessed data

### Vertical Scaling
- **Memory**: Increase RAM for large session processing
- **CPU**: Add more cores for parallel processing
- **Storage**: Use SSD for better I/O performance
- **Network**: Optimize bandwidth for API calls

### Auto-scaling
```bash
# Example auto-scaling script
#!/bin/bash
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)

if [ $CPU_USAGE -gt 80 ]; then
    # Scale up
    docker-compose up -d --scale thalamus-app=3
elif [ $CPU_USAGE -lt 30 ]; then
    # Scale down
    docker-compose up -d --scale thalamus-app=1
fi
```

## Maintenance

### Regular Maintenance Tasks
```bash
# Daily
- Monitor service status
- Check log files for errors
- Verify database backups

# Weekly
- Update system packages
- Review performance metrics
- Clean up old log files

# Monthly
- Review security updates
- Analyze performance trends
- Update documentation
```

### Update Procedures
```bash
# Application updates
cd /opt/thalamus
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart thalamus-app thalamus-refiner

# Database migrations (if needed)
python init_db.py
```

This deployment guide provides comprehensive instructions for setting up Thalamus in both development and production environments, with considerations for security, monitoring, and scalability. 