# Cloudflare DNS Manager Bot

A production-ready Telegram bot for managing Cloudflare DNS records via API. Built with aiogram 3.x and httpx.

## Features

- **Single-command operations** - Optimized for users with slow connections
- **Full DNS management** - List, add, update, delete, search records
- **Multiple record types** - A, AAAA, CNAME, TXT, MX, NS, SRV, CAA, PTR
- **Proxy control** - Toggle Cloudflare CDN proxy on/off
- **Multi-zone support** - Switch between different Cloudflare zones
- **Export functionality** - Export records as JSON
- **Secure** - Whitelist-based access control
- **Flexible deployment** - Polling or webhook mode

## Quick Start

### 1. Clone and Install Dependencies

```bash
cd CFBot
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Run the Bot

```bash
uv run python main.py
```

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with DNS edit permissions |
| `CLOUDFLARE_ZONE_ID` | Your Cloudflare zone ID |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs |

### Getting Cloudflare API Token

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Click "Create Token"
3. Use the "Edit zone DNS" template or create custom token with:
   - **Permissions**: Zone > DNS > Edit
   - **Zone Resources**: Include > Specific zone > Your domain
4. Copy the token to your `.env` file

### Getting Zone ID

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select your domain
3. On the Overview page, find "Zone ID" in the right sidebar
4. Copy it to your `.env` file

### Getting Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID
3. Add it to `ALLOWED_USER_IDS` in your `.env` file

## Usage

### Single-Line Commands (Primary - Best for Slow Connections)

These commands complete the operation in a single message:

```
# List records
/list              - List all DNS records
/list A            - List only A records
/list CNAME        - List only CNAME records

# Add records
/add sub A 1.2.3.4                    - Add A record with auto TTL
/add sub A 1.2.3.4 3600 true          - Add A record with TTL and proxy
/add www CNAME example.com            - Add CNAME record
/add mail MX mail.server.com          - Add MX record
/add _dmarc TXT "v=DMARC1; p=none"    - Add TXT record

# Update records
/update sub 5.6.7.8                   - Update record content
/update sub 5.6.7.8 3600              - Update with new TTL
/update sub 5.6.7.8 auto false        - Update with proxy off

# Delete records
/delete sub                           - Delete record (if unique)
/delete sub A                         - Delete specific type

# Other commands
/search mail            - Search records by name
/info sub.example.com   - Show detailed record info
/toggle_proxy sub       - Toggle CDN proxy status
/zones                  - List available zones
/zone <zone_id>         - Switch to different zone
/export                 - Export all records as JSON
/export A               - Export only A records
```

### Interactive Mode (Secondary - For Convenience)

Run commands without arguments for guided wizards:

```
/add       - Interactive record creation wizard
/update    - Interactive record update wizard
/delete    - Interactive record deletion wizard
```

### Command Parameters

| Parameter | Format | Examples |
|-----------|--------|----------|
| `name` | Short or full | `sub` or `sub.example.com` |
| `type` | Record type | `A`, `AAAA`, `CNAME`, `TXT`, `MX` |
| `content` | IP or hostname | `1.2.3.4`, `target.example.com` |
| `ttl` | Seconds or "auto" | `3600`, `auto`, `1` |
| `proxied` | Boolean | `true`, `false`, `yes`, `no` |

## Deployment

### Polling Mode (Development/Simple)

Best for development or when you don't have a public URL:

```bash
uv run python main.py
```

### Webhook Mode (Production)

For production deployment behind a reverse proxy:

1. Set up your `.env`:
```bash
USE_WEBHOOK=true
WEBHOOK_URL=https://your-domain.com
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8080
WEBHOOK_SECRET=your_random_secret
```

2. Run the bot:
```bash
uv run python main.py
```

3. Configure your reverse proxy (nginx example):
```nginx
location /webhook {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv sync

CMD ["uv", "run", "python", "main.py"]
```

### Systemd Service

Create `/etc/systemd/system/cfbot.service`:

```ini
[Unit]
Description=Cloudflare DNS Bot
After=network.target

[Service]
Type=simple
User=cfbot
WorkingDirectory=/opt/cfbot
ExecStart=/usr/local/bin/uv run python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable cfbot
sudo systemctl start cfbot
```

## Project Structure

```
CFBot/
├── bot/
│   ├── __init__.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py      # Single-line command handlers
│   │   ├── callbacks.py     # Inline keyboard callbacks
│   │   └── states.py        # FSM states for interactive flows
│   ├── services/
│   │   ├── __init__.py
│   │   └── cloudflare.py    # Cloudflare API wrapper
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── inline.py        # Inline keyboard builders
│   └── middlewares/
│       ├── __init__.py
│       └── auth.py          # User authentication middleware
├── main.py                  # Application entry point
├── .env.example             # Environment template
├── .gitignore
├── pyproject.toml
└── README.md
```

## Error Handling

The bot handles various error scenarios:

- **Invalid record types**: Shows valid options
- **API rate limits**: Displays Cloudflare error message
- **Network timeouts**: Retryable error message
- **Unauthorized users**: Access denied with user ID shown
- **Multiple matching records**: Prompts for selection
- **Confirmation for deletions**: Prevents accidental data loss

## Security Considerations

1. **Never commit `.env`** - It contains secrets
2. **Use API token, not Global API Key** - Limit permissions
3. **Whitelist users** - Only authorized IDs can use the bot
4. **Webhook secret** - Prevents unauthorized webhook calls
5. **HTTPS only** - Always use HTTPS for webhooks

## Troubleshooting

### Bot not responding
- Check `ALLOWED_USER_IDS` includes your Telegram user ID
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Check logs in `bot.log`

### Cloudflare API errors
- Verify `CLOUDFLARE_API_TOKEN` has DNS edit permissions
- Check `CLOUDFLARE_ZONE_ID` is correct
- Ensure the token has access to the specified zone

### Webhook not receiving updates
- Verify `WEBHOOK_URL` is publicly accessible
- Check SSL certificate is valid
- Verify `WEBHOOK_SECRET` matches in both Telegram and your config

## License

MIT License