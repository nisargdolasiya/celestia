# Celestia Discord Bot

A Discord bot that provides real-time aurora information, forecasts, and live camera feeds using the Auroras.live API. Perfect for aurora hunters and space weather enthusiasts!

## Features

- Real-time aurora probability for any location
- Current Kp index and forecasts
- Solar wind conditions (speed, density, magnetic field)
- Live aurora webcams from various locations
- Aurora activity charts and satellite images

## Commands

- `!aurora <latitude> <longitude>` - Get aurora information for a specific location
- `!cameras` - List all available aurora webcams
- `!charts` - List all available charts and graphs
- `!satellites` - List all available satellite images
- `!view <image_id>` - View a specific image

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your Discord bot token:
```
DISCORD_TOKEN=your_discord_bot_token_here
```

3. Run the bot:
```bash
python main.py
```

## Invite the Bot

[Click here to invite Celestia to your server](https://discord.com/api/oauth2/authorize?client_id=1360601374366371842&permissions=2147483648&scope=bot)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

