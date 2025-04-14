import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
from dotenv import load_dotenv
import datetime
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('celestia')

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or(''), intents=intents, help_command=None)

# Server configuration
GUILD_ID = 1360650689771995369
guild_object = discord.Object(id=GUILD_ID)

# API configuration
API_HEADERS = {
    'User-Agent': 'CelestiaDiscordBot/2.0 (ActiveDeveloper)',
    'Accept': 'application/json, image/*',
    'Cache-Control': 'no-cache'
}

# Image cache system
image_cache = {
    'last_updated': 0,
    'data': {}
}

@bot.event
async def on_ready():
    """Bot startup handler"""
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    await refresh_image_cache()
    update_task.start()
    
    try:
        await bot.tree.sync(guild=guild_object)
        logger.info('Successfully synced application commands')
    except Exception as error:
        logger.error(f'Command sync error: {error}')

@tasks.loop(minutes=15)
async def update_task():
    """Scheduled cache updates"""
    await refresh_image_cache()

async def refresh_image_cache(specific_image=None):
    """Refresh image cache from API"""
    try:
        api_url = "https://api.auroras.live/v1/?type=images&action=list"
        response = requests.get(api_url, headers=API_HEADERS, timeout=15)
        response.raise_for_status()
        
        fresh_data = response.json().get('images', {})
        current_timestamp = time.time()
        
        if specific_image:
            if specific_image in fresh_data:
                image_cache['data'][specific_image] = {
                    **fresh_data[specific_image],
                    'last_updated': current_timestamp
                }
        else:
            image_cache['data'] = {
                k: {**v, 'last_updated': current_timestamp}
                for k, v in fresh_data.items()
            }
            image_cache['last_updated'] = current_timestamp
        
    except requests.exceptions.RequestException as error:
        logger.error(f'API request failed: {error}')

def generate_aurora_embed(lat, lng, data, wind_data):
    """Create formatted embed for aurora data"""
    color_mapping = {
        'green': 0x00ff00,
        'yellow': 0xffff00,
        'orange': 0xffa500,
        'red': 0xff0000
    }
    
    embed = discord.Embed(
        title=f"Aurora Nowcast for {lat}°, {lng}°",
        color=color_mapping.get(data.get('color', '').lower(), 0x0000ff)
    )
    
    embed.add_field(name="Probability", value=f"{data.get('value', 0)}%", inline=True)
    embed.add_field(name="Status", value=data.get('color', 'Unknown').title(), inline=True)
    
    if wind_data:
        embed.add_field(
            name="Solar Wind",
            value=f"**Speed:** {wind_data.get('speed', 'N/A')} km/s\n"
                  f"**Density:** {wind_data.get('density', 'N/A')} p/cm³\n"
                  f"**Bz:** {wind_data.get('bz', 'N/A')} nT",
            inline=False
        )
    
    embed.set_footer(text=f"Data updated: {data.get('date', 'Unknown')}")
    return embed

@bot.tree.command(name="ping", description="Check bot responsiveness")
@app_commands.guilds(GUILD_ID)
async def ping_command(interaction: discord.Interaction):
    """Latency check command"""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"Celestia Operational\n"
        f"Latency: {latency}ms\n"
        f"Uptime: {datetime.datetime.now() - bot.start_time}"
    )

@bot.tree.command(name="aurora", description="Get aurora forecast for coordinates")
@app_commands.describe(
    latitude="Geographic latitude (-90 to 90)",
    longitude="Geographic longitude (-180 to 180)"
)
@app_commands.guilds(GUILD_ID)
async def aurora_command(
    interaction: discord.Interaction,
    latitude: app_commands.Range[float, -90, 90],
    longitude: app_commands.Range[float, -180, 180]
):
    """Aurora prediction command"""
    await interaction.response.defer()
    
    try:
        # Get timezone offset
        tz_offset = -datetime.datetime.now().astimezone().utcoffset().total_seconds() / 60
        
        # Prepare API request
        payload = {
            "nowcast:local": {"lat": latitude, "long": longitude},
            "format": {"date": {"tz": int(tz_offset)}}
        }
        
        # Fetch prediction data
        prediction_response = requests.post(
            "https://v2.api.auroras.live/nowcast",
            json=payload,
            headers=API_HEADERS,
            timeout=10
        )
        prediction_response.raise_for_status()
        prediction_data = prediction_response.json()
        
        # Fetch solar wind data
        wind_response = requests.get(
            "https://api.auroras.live/v1/?type=ace&data=all",
            headers=API_HEADERS,
            timeout=10
        )
        wind_data = wind_response.json() if wind_response.status_code == 200 else None
        
        # Create and send embed
        embed = generate_aurora_embed(latitude, longitude, prediction_data, wind_data)
        await interaction.followup.send(embed=embed)
        
    except requests.exceptions.RequestException as error:
        await interaction.followup.send(f"Data retrieval error: {str(error)}")
    except Exception as error:
        logger.error(f"Aurora command error: {error}")
        await interaction.followup.send("Error processing request")

@bot.tree.command(name="view", description="Display space weather resource")
@app_commands.describe(resource_id="ID from /cameras, /charts, or /satellites")
@app_commands.guilds(GUILD_ID)
async def view_command(interaction: discord.Interaction, resource_id: str):
    """Image display command"""
    await interaction.response.defer()
    
    await refresh_image_cache(specific_image=resource_id)
    resource_data = image_cache['data'].get(resource_id)
    
    if not resource_data:
        await interaction.followup.send("Resource not found")
        return
    
    try:
        image_url = f"{resource_data['url']}?t={int(time.time())}"
        embed = discord.Embed(title=resource_data['name'])
        embed.set_image(url=image_url)
        embed.set_footer(text=resource_data.get('description', ''))
        await interaction.followup.send(embed=embed)
    except Exception as error:
        logger.error(f"View command error: {error}")
        await interaction.followup.send("Error loading resource")

@bot.tree.command(name="cameras", description="List available aurora cameras")
@app_commands.guilds(GUILD_ID)
async def cameras_command(interaction: discord.Interaction):
    """Camera listing command"""
    await interaction.response.defer()
    await refresh_image_cache()
    
    camera_list = [
        (id, data) for id, data in image_cache['data'].items()
        if data.get('category') == 'cam' and 
        any(loc in data['name'].lower() for loc in ['yellowknife', 'rothney'])
    ]
    
    if not camera_list:
        await interaction.followup.send("No active cameras available")
        return
    
    embed = discord.Embed(title="Active Aurora Cameras")
    for cam_id, cam_data in camera_list:
        embed.add_field(
            name=cam_data['name'],
            value=f"ID: `{cam_id}`\n{cam_data.get('description', 'Live feed')}",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="charts", description="List available space weather charts")
@app_commands.guilds(GUILD_ID)
async def charts_command(interaction: discord.Interaction):
    """Chart listing command"""
    await interaction.response.defer()
    await refresh_image_cache()
    
    chart_list = [
        (id, data) for id, data in image_cache['data'].items()
        if data.get('category') == 'chart'
    ]
    
    if not chart_list:
        await interaction.followup.send("No charts available")
        return
    
    embed = discord.Embed(title="Space Weather Charts")
    for chart_id, chart_data in chart_list:
        embed.add_field(
            name=chart_data['name'],
            value=f"ID: `{chart_id}`\n{chart_data.get('description', 'Scientific data')}",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="satellites", description="List satellite imagery sources")
@app_commands.guilds(GUILD_ID)
async def satellites_command(interaction: discord.Interaction):
    """Satellite listing command"""
    await interaction.response.defer()
    await refresh_image_cache()
    
    satellite_list = [
        (id, data) for id, data in image_cache['data'].items()
        if data.get('category') == 'satellite'
    ]
    
    if not satellite_list:
        await interaction.followup.send("No satellite data available")
        return
    
    embed = discord.Embed(title="Satellite Imagery")
    for sat_id, sat_data in satellite_list:
        embed.add_field(
            name=sat_data['name'],
            value=f"ID: `{sat_id}`\n{sat_data.get('description', 'Orbital imagery')}",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="help", description="Show usage information")
@app_commands.guilds(GUILD_ID)
async def help_command(interaction: discord.Interaction):
    """Help command"""
    embed = discord.Embed(title="Celestia Bot Commands", color=0x109319)
    
    command_list = [
        ("/aurora", "Aurora predictions for coordinates"),
        ("/cameras", "Live aurora camera feeds"),
        ("/charts", "Space weather visualizations"),
        ("/satellites", "Satellite imagery sources"),
        ("/view", "Display specific resource by ID"),
        ("/ping", "Check bot status"),
        ("/help", "This help message")
    ]
    
    for name, value in command_list:
        embed.add_field(name=name, value=value, inline=False)
    
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    bot.start_time = datetime.datetime.now()
    bot.run(TOKEN)