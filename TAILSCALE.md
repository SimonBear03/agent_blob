# Tailscale Deployment Guide

This guide explains how to access Agent Blob from any device on your Tailscale network (phone, tablet, laptop, etc.).

## Prerequisites

- Tailscale installed on your home machine (server)
- Tailscale installed on devices you want to access from
- Both devices connected to the same Tailscale network (tailnet)

## Step 1: Get Your Tailscale Hostname

On your home machine, run:

```bash
tailscale status
```

Look for your machine's hostname, it will look like:
```
your-machine-name    user@email.com    linux   active; relay "xyz", tx 1234 rx 5678
```

Your full Tailscale hostname will be: `your-machine-name.tail-xxxxx.ts.net`

You can also find it in the Tailscale admin console: https://login.tailscale.com/admin/machines

## Step 2: Update Configuration

The `.env` file is already configured to allow Tailscale access (`SERVER_HOST=0.0.0.0`).

Update `NEXT_PUBLIC_API_URL` in `.env` with your Tailscale hostname:

```bash
# Replace with your actual Tailscale hostname
NEXT_PUBLIC_API_URL=http://your-machine-name.tail-xxxxx.ts.net:8000
```

## Step 3: Start the Servers

**Backend** (Terminal 1):
```bash
cd /Users/simon/Documents/GitHub/agent_blob/apps/server
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (Terminal 2):
```bash
cd /Users/simon/Documents/GitHub/agent_blob/apps/web
npm run dev -- --hostname 0.0.0.0
```

## Step 4: Access from Other Devices

On your phone, tablet, or other device:

1. Make sure Tailscale is running and connected
2. Open a browser
3. Navigate to: `http://your-machine-name.tail-xxxxx.ts.net:3000`

You should see the Agent Blob chat interface!

## Troubleshooting

### Can't connect from phone
- Verify both devices show "active" in `tailscale status`
- Check that servers are running on ports 8000 and 3000
- Try accessing the API directly: `http://your-machine.ts.net:8000` should show `{"status":"ok",...}`

### CORS errors
- The CORS middleware is configured to allow all `*.ts.net` domains
- If you see CORS errors, restart the FastAPI server

### API endpoint not found
- Make sure `NEXT_PUBLIC_API_URL` in `.env` matches your Tailscale hostname
- Restart the Next.js dev server after changing `.env`

## Using Tailscale Serve (Alternative - Easier & More Secure)

Tailscale Serve automatically sets up HTTPS and handles routing:

```bash
# Serve backend
tailscale serve https / http://127.0.0.1:8000

# Serve frontend (in another terminal)
tailscale serve https:3000 / http://127.0.0.1:3000
```

Then access via HTTPS:
- Frontend: `https://your-machine.ts.net:3000`
- Backend: `https://your-machine.ts.net`

Update `.env`:
```bash
NEXT_PUBLIC_API_URL=https://your-machine.ts.net
```

This is more secure as it uses HTTPS and you don't need to bind to `0.0.0.0`.

## Security Notes

- Tailscale provides encrypted connections between devices
- Only devices on your tailnet can access the servers
- Consider adding authentication for additional security
- The API key is always stored server-side and never exposed to the browser

## Performance Tips

- Tailscale uses direct connections when possible (peer-to-peer)
- If devices are on the same network, performance will be excellent
- Remote connections use DERP relays but are still quite fast
- Voice/streaming features may have higher latency over Tailscale

## Next Steps

Once working over Tailscale:
1. Set up systemd services for auto-start on boot
2. Consider Docker deployment for easier management
3. Add simple auth token for defense-in-depth security
4. Set up automatic backups of the SQLite database
