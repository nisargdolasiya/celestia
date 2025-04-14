import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
from dotenv import load_dotenv
import datetime
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('celestia')

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'), intents=intents, help_command=None)

# Guild ID for your server
GUILD_ID = 1360650689771995369
guild = discord.Object(id=GUILD_ID)

# Request headers
HEADERS = {
    'User-Agent': 'CelestiaDiscordBot/1.0',
    'Accept': 'image/jpeg,image/png,image/*',
    'Cache-Control': 'no-cache'
}

# Cache for image data
image_cache = {
    'last_update': 0,
    'images': {}
}

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    update_cache_loop.start()
    await update_image_cache()
    
    try:
        # Sync slash commands
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced for guild {GUILD_ID}")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

def is_cache_valid(image_id):
    if not image_cache.get('images') or image_id not in image_cache['images']:
        return False
    image_data = image_cache['images'][image_id]
    cache_duration = image_data.get('cache', 3600)
    last_update = image_data.get('last_update', 0)
    return time.time() - last_update < cache_duration

async def update_image_cache(specific_image=None, force_update=False):
    try:
        if specific_image:
            logger.info(f"Fetching fresh data for image: {specific_image}")
            response = requests.get(
                "https://api.auroras.live/v1/?type=images&action=list",
                headers=HEADERS,
                allow_redirects=True,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if specific_image in data.get('images', {}):
                image_data = data['images'][specific_image]
                image_response = requests.get(
                    image_data['url'],
                    headers=HEADERS,
                    allow_redirects=True,
                    timeout=10,
                    params={'t': int(time.time())}
                )
                image_response.raise_for_status()
                image_cache['images'][specific_image] = image_data
                image_data['last_update'] = time.time()
                logger.info(f"Successfully updated image {specific_image}")
        else:
            logger.info("Fetching fresh image list")
            response = requests.get(
                "https://api.auroras.live/v1/?type=images&action=list",
                headers=HEADERS,
                allow_redirects=True,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            new_images = data.get('images', {})
            current_time = time.time()
            
            if force_update:
                for img_id, img_data in new_images.items():
                    try:
                        image_response = requests.get(
                            img_data['url'],
                            headers=HEADERS,
                            allow_redirects=True,
                            timeout=10,
                            params={'t': int(current_time)}
                        )
                        image_response.raise_for_status()
                        img_data['last_update'] = current_time
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Error updating image {img_id}: {str(e)}")
            
            image_cache['images'] = new_images
            image_cache['last_update'] = current_time
            logger.info(f"Successfully updated cache with {len(new_images)} images")
            
    except requests.exceptions.Timeout:
        logger.error("Timeout while fetching images from API")
        if not image_cache.get('images'):
            image_cache['images'] = {}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error updating image cache: {str(e)}")
        if not image_cache.get('images'):
            image_cache['images'] = {}

@tasks.loop(minutes=5)
async def update_cache_loop():
    await update_image_cache()

@bot.tree.command(name="ping", description="Check the bot's latency")
@app_commands.guilds(GUILD_ID)
async def ping(interaction: discord.Interaction):
    start_time = time.time()
    await interaction.response.send_message(f"Pong! 🏓\nLatency: {round(bot.latency * 1000)} ms")
    end_time = time.time()
    response_time = round((end_time - start_time) * 1000)
    await interaction.edit_original_response(content=f"Pong! 🏓\nLatency: {round(bot.latency * 1000)} ms\nResponse Time: {response_time} ms")

@bot.tree.command(name="aurora", description="Get aurora information for a location")
@app_commands.describe(latitude="The latitude of the location", longitude="The longitude of the location")
@app_commands.guilds(GUILD_ID)
async def aurora(interaction: discord.Interaction, latitude: app_commands.Range[float, -90.0, 90.0], longitude: app_commands.Range[float, -180.0, 180.0]):
    await interaction.response.defer()
    try:
        tz_offset = -datetime.datetime.now().astimezone().utcoffset().total_seconds() / 60
        payload = {
            "nowcast:local": {
                "lat": latitude,
                "long": longitude,
            },
            "format": {
                "date": {
                    "tz": int(tz_offset)
                }
            }
        }

        response = requests.post(
            "https://v2.api.auroras.live/nowcast",
            json=payload,
            headers=HEADERS,
            allow_redirects=True,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        embed = discord.Embed(title="Aurora Nowcast", color=discord.Color.blue())
        embed.add_field(name="Location", value=f"Latitude: {latitude}°\nLongitude: {longitude}°", inline=False)

        color_meanings = {
            "green": "No chance",
            "yellow": "Slight chance",
            "orange": "Good chance",
            "red": "Almost certain"
        }
        embed.add_field(
            name="Aurora Probability",
            value=f"Value: {data.get('value')}%\nStatus: {color_meanings.get(data.get('color', '').lower(), 'Unknown')}",
            inline=False
        )

        wind_url = "https://api.auroras.live/v1/?type=ace&data=all"
        wind_response = requests.get(wind_url, headers=HEADERS, timeout=10)
        wind_response.raise_for_status()
        wind_data = wind_response.json()

        if wind_data and all(key in wind_data for key in ['speed', 'density', 'bz']):
            embed.add_field(
                name="Solar Wind",
                value=f"Speed: {wind_data['speed']} km/s\nDensity: {wind_data['density']} p/cm³\nBz: {wind_data['bz']} nT",
                inline=False
            )

        embed.add_field(
            name="Timestamps",
            value=f"Data from: {data.get('date')}\nRequest time: {data.get('request_date')}",
            inline=False
        )

        await interaction.followup.send(embed=embed)
    except requests.RequestException as e:
        await interaction.followup.send(f"Error fetching aurora data: {str(e)}")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="cameras", description="List all available aurora cameras")
@app_commands.guilds(GUILD_ID)
async def cameras(interaction: discord.Interaction):
    await interaction.response.defer()
    if not image_cache.get('images'):
        await update_image_cache()
    elif not is_cache_valid('cameras'):
        await update_image_cache()
    
    if not image_cache.get('images'):
        await interaction.followup.send("Error: Unable to fetch camera list")
        return

    embed = discord.Embed(
        title="Available Aurora Cameras",
        description="Currently active aurora cameras",
        color=discord.Color.blue()
    )

    active_cameras = {
        id: img for id, img in image_cache['images'].items() 
        if img.get('category') == 'cam' and 
        any(loc in img['name'].lower() for loc in ['yellowknife', 'rothney'])
    }

    for cam_id, cam_data in active_cameras.items():
        embed.add_field(
            name=cam_data['name'],
            value=f"ID: `{cam_id}`\n{cam_data['description']}",
            inline=False
        )

    if not active_cameras:
        embed.add_field(
            name="No Active Cameras",
            value="Currently no aurora cameras are active. Please try again later.",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="charts", description="List all available charts and graphs")
@app_commands.guilds(GUILD_ID)
async def charts(interaction: discord.Interaction):
    await interaction.response.defer()
    if not image_cache.get('images'):
        await update_image_cache()
    
    if not image_cache.get('images'):
        await interaction.followup.send("Error: Unable to fetch chart list")
        return

    embed = discord.Embed(
        title="Available Charts and Graphs",
        description="Use `/view <chart_id>` to view a specific chart",
        color=discord.Color.blue()
    )

    charts = {id: img for id, img in image_cache['images'].items() if img.get('category') == 'chart'}

    for chart_id, chart_data in charts.items():
        embed.add_field(
            name=chart_data['name'],
            value=f"ID: `{chart_id}`\n{chart_data['description']}",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="satellites", description="List all available satellite images")
@app_commands.guilds(GUILD_ID)
async def satellites(interaction: discord.Interaction):
    await interaction.response.defer()
    if not image_cache.get('images'):
        await update_image_cache()
    
    if not image_cache.get('images'):
        await interaction.followup.send("Error: Unable to fetch satellite image list")
        return

    embed = discord.Embed(
        title="Available Satellite Images",
        description="Use `/view <image_id>` to view a specific satellite image",
        color=discord.Color.blue()
    )

    satellites = {id: img for id, img in image_cache['images'].items() if img.get('category') == 'satellite'}

    for sat_id, sat_data in satellites.items():
        embed.add_field(
            name=sat_data['name'],
            value=f"ID: `{sat_id}`\n{sat_data['description']}",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="view", description="View a specific image by ID")
@app_commands.describe(image_id="The ID of the image to view")
@app_commands.guilds(GUILD_ID)
async def view(interaction: discord.Interaction, image_id: str):
    await interaction.response.defer()
    try:
        await update_image_cache(specific_image=image_id, force_update=True)
        
        if image_id not in image_cache.get('images', {}):
            await interaction.followup.send(f"Error: Image ID '{image_id}' not found. Use /cameras, /charts, or /satellites to see available images.")
            return

        image_data = image_cache['images'][image_id]
        current_time = int(time.time())
        image_url = f"{image_data['url']}{'&' if '?' in image_data['url'] else '?'}t={current_time}"
        
        embed = discord.Embed(
            title=image_data['name'],
            description=image_data['description'],
            color=discord.Color.blue()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Real-time image")
        
        logger.info(f"Sending real-time image for {image_id}")
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"Error: Unable to fetch the image. Please try again.")
        logger.error(f"Error in view command for {image_id}: {str(e)}")

@bot.tree.command(name="help", description="Show all available commands")
@app_commands.guilds(GUILD_ID)
async def help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Celestia Bot Commands",
        description="Here are all the available commands:",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="Aurora Commands",
        value="`/aurora <latitude> <longitude>` - Get aurora information for a location\n"
              "Example: `/aurora 64.5 -147.5` (Fairbanks, Alaska)",
        inline=False
    )

    embed.add_field(
        name="Image Commands",
        value="`/cameras` - List available aurora webcams\n"
              "`/charts` - List available charts and graphs\n"
              "`/satellites` - List available satellite images\n"
              "`/view <image_id>` - View a specific image",
        inline=False
    )

    embed.add_field(
        name="Utility Commands",
        value="`/ping` - Check bot latency\n"
              "`/help` - Show this help message",
        inline=False
    )

    embed.set_footer(text="For more help, join our support server or visit our GitHub page")
    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)