import os
import discord
from discord.ext import commands, tasks
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
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

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

def is_cache_valid(image_id):
    """Check if the cached image data is still valid"""
    if not image_cache.get('images') or image_id not in image_cache['images']:
        return False
    
    image_data = image_cache['images'][image_id]
    cache_duration = image_data.get('cache', 3600)  # Default to 1 hour if not specified
    last_update = image_data.get('last_update', 0)
    return time.time() - last_update < cache_duration

async def update_image_cache(specific_image=None, force_update=False):
    """Update the cache of available images from the API"""
    try:
        if specific_image:
            # Always fetch fresh data for specific image requests
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
                # Always fetch the latest image
                image_response = requests.get(
                    image_data['url'],
                    headers=HEADERS,
                    allow_redirects=True,
                    timeout=10,
                    params={'t': int(time.time())}  # Add timestamp to bypass cache
                )
                image_response.raise_for_status()
                
                # Update cache with fresh data
                image_cache['images'][specific_image] = image_data
                image_data['last_update'] = time.time()
                logger.info(f"Successfully updated image {specific_image}")
        else:
            # Update all images
            logger.info("Fetching fresh image list")
            response = requests.get(
                "https://api.auroras.live/v1/?type=images&action=list",
                headers=HEADERS,
                allow_redirects=True,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Always update with fresh data
            new_images = data.get('images', {})
            current_time = time.time()
            
            # If forcing update, fetch fresh images for all
            if force_update:
                for img_id, img_data in new_images.items():
                    try:
                        # Fetch fresh image
                        image_response = requests.get(
                            img_data['url'],
                            headers=HEADERS,
                            allow_redirects=True,
                            timeout=10,
                            params={'t': int(current_time)}  # Add timestamp to bypass cache
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
    """Periodically update the image cache"""
    await update_image_cache()

@bot.command(name='aurora')
async def aurora(ctx, lat: float = None, long: float = None):
    """Get aurora information for a specific location"""
    if lat is None or long is None:
        await ctx.send("Please provide both latitude and longitude. Usage: !aurora <latitude> <longitude>")
        return

    if not (-90 <= lat <= 90) or not (-180 <= long <= 180):
        await ctx.send("Invalid coordinates! Latitude must be between -90 and 90, and longitude between -180 and 180.")
        return

    try:
        # Get timezone offset in minutes
        tz_offset = -datetime.datetime.now().astimezone().utcoffset().total_seconds() / 60

        # Prepare request payload
        payload = {
            "nowcast:local": {
                "lat": lat,
                "long": long,
            },
            "format": {
                "date": {
                    "tz": int(tz_offset)
                }
            }
        }

        # Make POST request to v2 API
        response = requests.post(
            "https://v2.api.auroras.live/nowcast",
            json=payload,
            headers=HEADERS,
            allow_redirects=True,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Create an embed with the information
        embed = discord.Embed(
            title="Aurora Nowcast",
            color=discord.Color.blue()
        )

        # Add location information
        embed.add_field(
            name="Location",
            value=f"Latitude: {lat}°\nLongitude: {long}°",
            inline=False
        )

        # Add probability information
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

        # Get solar wind data from v1 API
        wind_url = "https://api.auroras.live/v1/?type=ace&data=all"
        wind_response = requests.get(wind_url, headers=HEADERS, allow_redirects=True, timeout=10)
        wind_response.raise_for_status()
        wind_data = wind_response.json()

        # wind parameters from the response
        if wind_data and all(key in wind_data for key in ['speed', 'density', 'bz']):
            embed.add_field(
                name="Solar Wind",
                value=f"Speed: {wind_data['speed']} km/s\n"
                      f"Density: {wind_data['density']} p/cm³\n"
                      f"Bz: {wind_data['bz']} nT",
                inline=False
            )

        # Add timestamps
        embed.add_field(
            name="Timestamps",
            value=f"Data from: {data.get('date')}\nRequest time: {data.get('request_date')}",
            inline=False
        )

        await ctx.send(embed=embed)

    except requests.RequestException as e:
        await ctx.send(f"Error fetching aurora data: {str(e)}")
        print(f"Full error: {e.response.text if hasattr(e, 'response') else str(e)}")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command(name='cameras')
async def list_cameras(ctx):
    """List all available aurora cameras"""
    # Only update cache if needed
    if not image_cache.get('images'):
        await update_image_cache()
    elif not is_cache_valid('cameras'):
        await update_image_cache()
    
    if not image_cache.get('images'):
        await ctx.send("Error: Unable to fetch camera list")
        return

    embed = discord.Embed(
        title="Available Aurora Cameras",
        description="Currently active aurora cameras",
        color=discord.Color.blue()
    )

    # Only show Yellowknife and Rothney cameras
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

    await ctx.send(embed=embed)

@bot.command(name='charts')
async def list_charts(ctx):
    """List all available charts and graphs"""
    if not image_cache.get('images'):
        await update_image_cache()
    
    if not image_cache.get('images'):
        await ctx.send("Error: Unable to fetch chart list")
        return

    embed = discord.Embed(
        title="Available Charts and Graphs",
        description="Use `!view <chart_id>` to view a specific chart",
        color=discord.Color.blue()
    )

    charts = {id: img for id, img in image_cache['images'].items() 
             if img.get('category') == 'chart'}

    for chart_id, chart_data in charts.items():
        embed.add_field(
            name=chart_data['name'],
            value=f"ID: `{chart_id}`\n{chart_data['description']}",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command(name='satellites')
async def list_satellites(ctx):
    """List all available satellite images"""
    if not image_cache.get('images'):
        await update_image_cache()
    
    if not image_cache.get('images'):
        await ctx.send("Error: Unable to fetch satellite image list")
        return

    embed = discord.Embed(
        title="Available Satellite Images",
        description="Use `!view <image_id>` to view a specific satellite image",
        color=discord.Color.blue()
    )

    satellites = {id: img for id, img in image_cache['images'].items() 
                 if img.get('category') == 'satellite'}

    for sat_id, sat_data in satellites.items():
        embed.add_field(
            name=sat_data['name'],
            value=f"ID: `{sat_id}`\n{sat_data['description']}",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command(name='view')
async def view_image(ctx, image_id: str):
    """View a specific aurora camera, chart, or satellite image"""
    try:
        # Always force a fresh update for the specific image
        await update_image_cache(specific_image=image_id, force_update=True)
        
        if image_id not in image_cache.get('images', {}):
            await ctx.send(f"Error: Image ID '{image_id}' not found. Use !cameras, !charts, or !satellites to see available images.")
            return

        image_data = image_cache['images'][image_id]
        current_time = int(time.time())
        
        # Add timestamp to URL to bypass cache
        image_url = f"{image_data['url']}{'&' if '?' in image_data['url'] else '?'}t={current_time}"
        
        embed = discord.Embed(
            title=image_data['name'],
            description=image_data['description'],
            color=discord.Color.blue()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Real-time image")
        
        logger.info(f"Sending real-time image for {image_id}")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"Error: Unable to fetch the image. Please try again.")
        logger.error(f"Error in view_image command for {image_id}: {str(e)}")

@bot.command(name='help')
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title="Celestia Bot Commands",
        description="Here are all the available commands:",
        color=discord.Color.blue()
    )

    # Aurora Information
    embed.add_field(
        name="Aurora Commands",
        value="`!aurora <latitude> <longitude>` - Get aurora information for a location\n"
              "Example: `!aurora 64.5 -147.5` (Fairbanks, Alaska)",
        inline=False
    )

    # Image Commands
    embed.add_field(
        name="Image Commands",
        value="`!cameras` - List all available aurora webcams\n"
              "`!charts` - List all available charts and graphs\n"
              "`!satellites` - List all available satellite images\n"
              "`!view <image_id>` - View a specific image",
        inline=False
    )

    # Help Command
    embed.add_field(
        name="Help",
        value="`!help` - Show this help message",
        inline=False
    )

    # Add footer with support info
    embed.set_footer(text="For more help, join our support server or visit our GitHub page")

    await ctx.send(embed=embed)

# Run the bot
bot.run(TOKEN)
