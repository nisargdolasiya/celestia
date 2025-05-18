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
OWNER_ID = os.getenv('OWNER_ID', '')  # Default to empty string if not found
GUILD_ID = os.getenv('GUILD_ID', '')  # Default to empty string if not found

# Print environment variables for debugging (will only show in logs)
print(f"OWNER_ID set to: '{OWNER_ID}'")
print(f"GUILD_ID set to: '{GUILD_ID}'")

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
# Using a command prefix that won't be triggered accidentally
bot = commands.Bot(command_prefix=commands.when_mentioned_or(None), intents=intents, help_command=None)

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

# List of inactive charts to filter out
INACTIVE_CHARTS = {
    'goes1315',
    'hobartmag',
    'launcestonmag',
    'hobartkindex',
    'launcestonkindex',
    'wing-kp-12-hour',
    'goes-magnetometer'
}

@bot.event
async def on_message(message):
    # Ignore all message content - only process slash commands
    # Only process messages that are necessary for the bot to function
    if message.author.id == bot.user.id:
        return
    
    # Don't process any commands through the prefix system
    # This ensures only slash commands will work
    return

@bot.event
async def on_ready():
    """Bot startup handler"""
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    await refresh_image_cache()
    update_task.start()

    try:
        # Sync commands globally and to the owner's guild
        await bot.tree.sync()
        logger.info('Successfully synced application commands globally')
        
        # If owner guild is set, also sync commands there
        if GUILD_ID:
            owner_guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=owner_guild)
            await bot.tree.sync(guild=owner_guild)
            logger.info(f'Successfully synced commands to guild ID: {GUILD_ID}')
    except Exception as error:
        logger.error(f'Command sync error: {error}')

@bot.tree.command(name="ping", description="Check bot latency")
async def ping_command(interaction: discord.Interaction):
    """Latency check command"""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"Celestia Operational\n"
        f"Latency: {latency}ms\n"
        f"Uptime: {datetime.datetime.now() - bot.start_time}"
    )

@bot.tree.command(name="aurora", description="Get aurora prediction for a location")
@app_commands.describe(
    latitude="Latitude (-90 to 90)",
    longitude="Longitude (-180 to 180)"
)
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

@bot.tree.command(name="view", description="View a specific resource")
@app_commands.describe(resource_id="ID of the resource to view")
async def view_command(interaction: discord.Interaction, resource_id: str):
    """Image display command"""
    await interaction.response.defer()
    
    # Check if the requested resource is an inactive chart
    if resource_id in INACTIVE_CHARTS:
        await interaction.followup.send("This chart is currently inactive and unavailable.")
        return
    
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

@bot.tree.command(name="cameras", description="List available cameras")
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

@bot.tree.command(name="charts", description="List available charts")
async def charts_command(interaction: discord.Interaction):
    """Chart listing command"""
    await interaction.response.defer()
    await refresh_image_cache()
    
    chart_list = [
        (id, data) for id, data in image_cache['data'].items()
        if data.get('category') == 'chart' and id not in INACTIVE_CHARTS
    ]
    
    if not chart_list:
        await interaction.followup.send("No active charts available")
        return
    
    embed = discord.Embed(title="Space Weather Charts")
    for chart_id, chart_data in chart_list:
        embed.add_field(
            name=chart_data['name'],
            value=f"ID: `{chart_id}`\n{chart_data.get('description', 'Scientific data')}",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="satellites", description="List available satellite images")
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

@bot.tree.command(name="help", description="Show bot commands and info")
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

@bot.tree.command(name="servers", description="List servers the bot is in", guild=discord.Object(id=int(GUILD_ID)) if GUILD_ID else None)
async def servers_command(interaction: discord.Interaction):
    """Server listing command (Owner only, minimal info with improved owner retrieval)"""
    # Debug info to help identify the user's ID
    user_id = str(interaction.user.id)
    print(f"User trying to use /servers: {interaction.user} (ID: {user_id})")
    print(f"Expected OWNER_ID: '{OWNER_ID}'")
    print(f"Do they match? {user_id == OWNER_ID}")
    
    # Double-check permission in case the decorator check fails
    if not OWNER_ID or str(interaction.user.id) != OWNER_ID:
        await interaction.response.send_message(f"This command is restricted to the bot owner only.", ephemeral=True)
        return
        
    # Optional guild restriction if GUILD_ID is set
    if GUILD_ID and str(interaction.guild_id) != GUILD_ID:
        await interaction.response.send_message("This command can only be used in the designated owner guild.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # Sort guilds by member count (descending)
    sorted_guilds = sorted(bot.guilds, key=lambda g: len(g.members), reverse=True)

    # Discord purple color for the embed
    embed_color = discord.Color.blurple()

    # Pagination setup
    guilds_per_page = 10
    total_guilds = len(sorted_guilds)
    total_pages = (total_guilds + guilds_per_page - 1) // guilds_per_page

    # Create cache for owners
    owner_cache = {}

    async def get_owner(guild):
        """Get owner with multiple fallback methods to ensure we get the owner"""
        if guild.id in owner_cache:
            return owner_cache[guild.id]
            
        try:
            # First try from guild.owner attribute if available
            if guild.owner:
                owner_cache[guild.id] = guild.owner
                return guild.owner
                
            # Try to get the owner from members using owner_id
            owner_member = guild.get_member(guild.owner_id)
            if owner_member:
                owner_cache[guild.id] = owner_member
                return owner_member
                
            # Last resort, try fetch_member for the owner
            owner = await guild.fetch_member(guild.owner_id)
            owner_cache[guild.id] = owner
            return owner
        except Exception as e:
            # If all methods fail, create a minimal fake user with just the ID
            try:
                # At least get the owner ID if nothing else works
                owner_id = guild.owner_id
                return {"id": owner_id, "name": f"Unknown User ({owner_id})"}
            except:
                return None

    def make_embed(page: int):
        embed = discord.Embed(
            title=f"Server List (Page {page+1}/{total_pages})",
            description=f"Currently in {total_guilds} servers with {sum(len(g.members) for g in bot.guilds):,} total members.",
            color=embed_color
        )
        
        start = page * guilds_per_page
        end = min(start + guilds_per_page, total_guilds)
        
        for idx, guild in enumerate(sorted_guilds[start:end], start=start):
            # Join date in a simple format
            join_date = guild.me.joined_at.strftime("%Y-%m-%d") if guild.me.joined_at else "Unknown"
            
            embed.add_field(
                name=f"{guild.name} ({guild.id})",
                value=f"Members: {len(guild.members)}\nJoined: {join_date}\nOwner: Loading...",
                inline=False
            )
        return embed, start, end

    async def update_owners(embed, page_start, page_end):
        for idx, guild in enumerate(sorted_guilds[page_start:page_end], start=page_start):
            owner = await get_owner(guild)
            field_idx = idx - page_start
            
            owner_str = "Unknown"
            if owner:
                if isinstance(owner, dict):
                    # This is our minimal fake user with just ID
                    owner_id = owner["id"]
                    owner_str = f"ID: {owner_id}"
                else:
                    # This is a real discord.Member or discord.User
                    # Show username and tag if available, plus ID
                    try:
                        if hasattr(owner, "name") and owner.name:
                            if hasattr(owner, "discriminator") and owner.discriminator and owner.discriminator != "0":
                                owner_str = f"{owner.name}#{owner.discriminator} (ID: {owner.id})"
                            else:
                                owner_str = f"{owner.name} (ID: {owner.id})"
                        else:
                            owner_str = f"ID: {owner.id}"
                    except Exception:
                        # If something goes wrong, at least show the ID
                        owner_str = f"ID: {owner.id}"
                
            # Get the current field value and update only the owner part
            current_value = embed.fields[field_idx].value
            new_value = current_value.replace("Owner: Loading...", f"Owner: {owner_str}")
            embed.set_field_at(
                field_idx,
                name=embed.fields[field_idx].name,
                value=new_value,
                inline=False
            )
            
        return embed

    # Initial embed
    initial_embed, start_idx, end_idx = make_embed(0)
    message = await interaction.followup.send(embed=initial_embed, ephemeral=True)
    
    # For single page, just update and return
    if total_pages == 1:
        updated_embed = await update_owners(initial_embed, start_idx, end_idx)
        await message.edit(embed=updated_embed)
        return

    # For multiple pages, add navigation buttons
    class PageView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0
            self.message = None

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
        async def previous(self, interaction_: discord.Interaction, button: discord.ui.Button):
            if self.page > 0:
                self.page -= 1
                new_embed, start, end = make_embed(self.page)
                await interaction_.response.edit_message(embed=new_embed, view=self)
                self.message = await interaction_.original_response()
                updated_embed = await update_owners(new_embed, start, end)
                await self.message.edit(embed=updated_embed)
            else:
                await interaction_.response.defer()

        @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
        async def next(self, interaction_: discord.Interaction, button: discord.ui.Button):
            if self.page < total_pages - 1:
                self.page += 1
                new_embed, start, end = make_embed(self.page)
                await interaction_.response.edit_message(embed=new_embed, view=self)
                self.message = await interaction_.original_response()
                updated_embed = await update_owners(new_embed, start, end)
                await self.message.edit(embed=updated_embed)
            else:
                await interaction_.response.defer()

        @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
        async def refresh(self, interaction_: discord.Interaction, button: discord.ui.Button):
            new_embed, start, end = make_embed(self.page)
            await interaction_.response.edit_message(embed=new_embed, view=self)
            self.message = await interaction_.original_response()
            updated_embed = await update_owners(new_embed, start, end)
            await self.message.edit(embed=updated_embed)

    view = PageView()
    await message.edit(view=view)
    view.message = message
    
    # Update the initial page's owner info
    updated_embed = await update_owners(initial_embed, start_idx, end_idx)
    await message.edit(embed=updated_embed)

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
            if specific_image in fresh_data and specific_image not in INACTIVE_CHARTS:
                image_cache['data'][specific_image] = {
                    **fresh_data[specific_image],
                    'last_updated': current_timestamp
                }
        else:
            # Filter out inactive charts when caching all data
            image_cache['data'] = {
                k: {**v, 'last_updated': current_timestamp}
                for k, v in fresh_data.items()
                if k not in INACTIVE_CHARTS
            }
            image_cache['last_updated'] = current_timestamp
        
    except requests.exceptions.RequestException as error:
        logger.error(f'API request failed: {error}')

def generate_aurora_embed(lat, lng, data, wind_data):
    """Create formatted embed for aurora data"""
    status_messages = {
        'green': ('No Chance', 0x00ff00),
        'yellow': ('Slight Chance', 0xffff00),
        'orange': ('Good Chance', 0xffa500),
        'red': ('Almost Certain', 0xff0000)
    }
    
    status, color = status_messages.get(data.get('color', '').lower(), (0x0000ff, 'Unknown Status'))
    
    embed = discord.Embed(
        title=f"Aurora Nowcast for {lat}°, {lng}°",
        color=color,
        description=f"**Current Status:** {status}"
    )
    
    embed.add_field(name="Probability", value=f"{data.get('value', 0)}%", inline=True)
    
    if wind_data:
        embed.add_field(
            name="Solar Wind Conditions",
            value=f"**Speed:** {wind_data.get('speed', 'N/A')} km/s\n"
                  f"**Density:** {wind_data.get('density', 'N/A')} p/cm³\n"
                  f"**Bz:** {wind_data.get('bz', 'N/A')} nT",
            inline=False
        )
    
    embed.set_footer(text=f"Data updated: {data.get('date', 'Unknown')}")
    return embed

if __name__ == "__main__":
    bot.start_time = datetime.datetime.now()
    bot.run(TOKEN)