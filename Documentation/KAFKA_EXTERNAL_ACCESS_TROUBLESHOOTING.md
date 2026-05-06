# Kafka External Access Troubleshooting Guide

## Error: "KafkaTimeoutError: Failed to update metadata after 60.0 secs"

This error occurs when:
1. ✅ TCP connection works (you can reach port 9092)
2. ❌ Kafka metadata fetch fails (Kafka tells client wrong address)

## Root Cause

When an external client connects to `160.40.52.44:9092`, Kafka responds with its **advertised listeners**. If Kafka is advertising `localhost:9092` or `kafka:29092`, the external client tries to connect to those addresses and fails.

## Solution Steps

### Step 1: Verify Current Configuration

Check your `docker-compose.yml`:

```yaml
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://160.40.52.44:9092
```

**Must have:**
- `PLAINTEXT://kafka:29092` - for internal Docker communication
- `PLAINTEXT_HOST://160.40.52.44:9092` - for external access (your external IP)

### Step 2: Fully Restart Kafka

**IMPORTANT:** A simple `restart` might not pick up configuration changes. Do a full restart:

```bash
# Stop Kafka
docker-compose stop kafka

# Remove the container (this ensures fresh start)
docker-compose rm -f kafka

# Start Kafka with new configuration
docker-compose up -d kafka

# Wait for Kafka to start (check logs)
docker-compose logs -f kafka
```

Look for this in the logs:
```
[KafkaServer id=1] started (kafka.server.KafkaServer)
```

### Step 3: Verify Kafka Configuration

Check what Kafka is actually advertising:

```bash
# Enter Kafka container
docker exec -it data-warehouse-kafka bash

# Check environment variables
env | grep KAFKA_ADVERTISED

# Should show:
# KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:29092,PLAINTEXT_HOST://160.40.52.44:9092
```

### Step 4: Test from Server Itself

First, test from the server where Kafka is running:

```bash
# On the Kafka server
python test_kafka_quick.py localhost:9092
```

This should work. If it doesn't, there's a different issue.

### Step 5: Test from External Machine

```bash
# On external machine
python test_kafka_external.py --broker 160.40.52.44:9092
```

This will give detailed diagnostics.

## Common Issues

### Issue 1: Configuration Not Applied

**Symptom:** Restart didn't fix it

**Solution:**
```bash
# Full restart with config reload
docker-compose down kafka
docker-compose up -d kafka
```

### Issue 2: Wrong IP Address

**Symptom:** Still getting timeout

**Check:**
```bash
# On the server, find the actual external IP
curl ifconfig.me
# or
hostname -I
```

Update `docker-compose.yml` with the correct IP.

### Issue 3: Firewall Blocking

**Symptom:** TCP connection test fails

**Check:**
```bash
# On external machine
telnet 160.40.52.44 9092
# or
nc -zv 160.40.52.44 9092
```

**Solution:** Open port 9092 in firewall:
```bash
# Ubuntu/Debian
sudo ufw allow 9092/tcp

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=9092/tcp
sudo firewall-cmd --reload
```

### Issue 4: Docker Port Mapping

**Check:**
```bash
# Verify port is mapped
docker ps | grep kafka
# Should show: 0.0.0.0:9092->9092/tcp

# Check if port is listening
netstat -tlnp | grep 9092
# or
ss -tlnp | grep 9092
```

## Verification Commands

### On Kafka Server:

```bash
# 1. Check Kafka is running
docker ps | grep kafka

# 2. Check Kafka logs
docker logs data-warehouse-kafka | tail -50

# 3. Check advertised listeners in logs
docker logs data-warehouse-kafka | grep -i "advertised"

# 4. Test local connection
python test_kafka_quick.py localhost:9092
```

### On External Machine:

```bash
# 1. Test TCP connectivity
telnet 160.40.52.44 9092
# or
nc -zv 160.40.52.44 9092

# 2. Run diagnostic test
python test_kafka_external.py --broker 160.40.52.44:9092
```

## Expected Behavior

### ✅ Working Configuration:

1. **TCP Test:** ✅ Connection successful
2. **Metadata Test:** ✅ Kafka responds with correct advertised address
3. **Produce Test:** ✅ Message sent successfully

### ❌ Broken Configuration:

1. **TCP Test:** ✅ Connection successful (port is open)
2. **Metadata Test:** ❌ Timeout (Kafka advertising wrong address)
3. **Produce Test:** ❌ Timeout (can't connect to advertised address)

## Quick Fix Script

If you've updated `docker-compose.yml` but it's still not working:

```bash
#!/bin/bash
# Full Kafka restart script

echo "Stopping Kafka..."
docker-compose stop kafka

echo "Removing Kafka container..."
docker-compose rm -f kafka

echo "Starting Kafka..."
docker-compose up -d kafka

echo "Waiting for Kafka to start..."
sleep 10

echo "Checking Kafka logs..."
docker logs data-warehouse-kafka | tail -20

echo "Testing local connection..."
python test_kafka_quick.py localhost:9092
```

Save as `restart_kafka.sh`, make executable: `chmod +x restart_kafka.sh`, then run: `./restart_kafka.sh`

## Still Not Working?

1. **Check Kafka logs for errors:**
   ```bash
   docker logs data-warehouse-kafka
   ```

2. **Verify network configuration:**
   ```bash
   docker network inspect data-warehouse-network
   ```

3. **Test with kafka-python directly:**
   ```python
   from kafka import KafkaProducer
   producer = KafkaProducer(bootstrap_servers=['160.40.52.44:9092'])
   # This will show the exact error
   ```

4. **Check if multiple listeners are causing issues:**
   - Try using only `PLAINTEXT_HOST` listener
   - Or ensure client is using the correct listener name
