import os
import discord
from discord.ext import commands
import requests
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Cache for image data
image_cache = {}

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await update_image_cache()

async def update_image_cache():
    """Update the cache of available images from the API"""
    try:
        response = requests.get("https://api.auroras.live/v1/?type=images&action=list")
        response.raise_for_status()
        data = response.json()
        global image_cache
        image_cache = data
    except Exception as e:
        print(f"Error updating image cache: {e}")

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
            json=payload
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
        wind_response = requests.get(wind_url)
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
    if not image_cache:
        await update_image_cache()
    
    if not image_cache:
        await ctx.send("Error: Unable to fetch camera list")
        return

    embed = discord.Embed(
        title="Available Aurora Cameras",
        description="Use `!view <camera_id>` to view a specific camera",
        color=discord.Color.blue()
    )

    cameras = {id: img for id, img in image_cache.get('images', {}).items() 
              if img.get('category') == 'cam'}

    for cam_id, cam_data in cameras.items():
        embed.add_field(
            name=cam_data['name'],
            value=f"ID: `{cam_id}`\n{cam_data['description']}",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command(name='charts')
async def list_charts(ctx):
    """List all available charts and graphs"""
    if not image_cache:
        await update_image_cache()
    
    if not image_cache:
        await ctx.send("Error: Unable to fetch chart list")
        return

    embed = discord.Embed(
        title="Available Charts and Graphs",
        description="Use `!view <chart_id>` to view a specific chart",
        color=discord.Color.blue()
    )

    charts = {id: img for id, img in image_cache.get('images', {}).items() 
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
    if not image_cache:
        await update_image_cache()
    
    if not image_cache:
        await ctx.send("Error: Unable to fetch satellite image list")
        return

    embed = discord.Embed(
        title="Available Satellite Images",
        description="Use `!view <image_id>` to view a specific satellite image",
        color=discord.Color.blue()
    )

    satellites = {id: img for id, img in image_cache.get('images', {}).items() 
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
    if not image_cache:
        await update_image_cache()
    
    if not image_cache or 'images' not in image_cache:
        await ctx.send("Error: Unable to fetch image data")
        return

    if image_id not in image_cache['images']:
        await ctx.send(f"Error: Image ID '{image_id}' not found. Use !cameras, !charts, or !satellites to see available images.")
        return

    image_data = image_cache['images'][image_id]
    
    embed = discord.Embed(
        title=image_data['name'],
        description=image_data['description'],
        color=discord.Color.blue()
    )
    embed.set_image(url=image_data['url'])
    embed.set_footer(text=f"Cache time: {image_data['cache']} seconds")

    await ctx.send(embed=embed)

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
