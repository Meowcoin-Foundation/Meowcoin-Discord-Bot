#bot.py
import discord
from discord.ext import commands, tasks
import aiohttp
import time
import os
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Get Discord bot token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Define intents to enable message and member events
intents = discord.Intents.default()
intents.messages = True
intents.members = True

# Create a Discord bot instance
client = commands.Bot(command_prefix="!", intents=intents)

# Define a global variable to store the last notification time
last_notification_time = 0

# Function to make RPC calls to the new Meowcoin RPC endpoint
async def make_rpc_call(session, method, params=None):
    """
    Make an RPC call to the Meowcoin RPC endpoint
    """
    if params is None:
        params = []
    
    try:
        payload = {
            "method": method,
            "params": params
        }
        
        async with session.post(
            "https://mewc-rpc-mainnet.mewccrypto.com/rpc",
            headers={"Content-Type": "application/json"},
            json=payload
        ) as response:
            data = await response.json()
            return data.get("result")
    except Exception as e:
        print(f"Error making RPC call {method}: {e}")
        return None

# Function to set a voice channel to private (disconnect for everyone)
async def set_channel_private(category, channel):
    try:
        if isinstance(channel, discord.VoiceChannel) and channel.category == category:
            await channel.set_permissions(channel.guild.default_role, connect=False)
    except Exception as e:
        print(f"An error occurred while setting channel to private: {e}")

# Function to get or create a voice channel within a category
async def get_or_create_channel(category, channel_name):
    for existing_channel in category.voice_channels:
        existing_name = existing_channel.name.lower().replace(" ", "")
        target_name = channel_name.lower().replace(" ", "")
        if existing_name.startswith(target_name):
            return existing_channel

    channel = await category.create_voice_channel(channel_name)
    time.sleep(0.5)
    return channel

# Function to create or update a voice channel's name with specific formatting
async def create_or_update_channel(guild, category, channel_name, stat_value):
    try:
        channel = await get_or_create_channel(category, channel_name)

        if isinstance(stat_value, str) and stat_value == "N/A":
            formatted_value = stat_value
        else:
            if channel_name.lower() == "members:":
                formatted_value = "{:,.0f}".format(stat_value)
            elif channel_name.lower() == "supply:":
                formatted_value = "{:,.2f}B MEWC".format(stat_value)
            elif channel_name.lower() == "price: $":
                formatted_value = "{:.6f}".format(stat_value)
            elif channel_name.lower() in ["hashrate (meowpow): gh/s", "hashrate (script): gh/s"]:
                formatted_value = "{:,.3f}".format(stat_value)
            elif channel_name.lower() == "market cap:":
                formatted_value = "{:,.0f}".format(round(stat_value))
            elif channel_name.lower() in ["difficulty (meowpow):", "difficulty (script):", "block:"]:
                formatted_value = "{:,.0f}".format(stat_value)
            elif channel_name.lower() == "24h volume:":
                formatted_value = "{:,.0f}".format(stat_value)
            else:
                formatted_value = stat_value

        await channel.edit(name=f"{channel_name} {formatted_value}")

    except Exception as e:
        print(f"An error occurred while updating channel name: {e}")

# Function to update all statistics channels within a guild
async def update_stats_channels(guild):
    global last_notification_time

    try:
        # Fetch server statistics from the APIs
        async with aiohttp.ClientSession() as session:
            # Get difficulty values using RPC
            try:
                difficulty_meowpow = await make_rpc_call(session, "getdifficulty", [0])
                if difficulty_meowpow is None:
                    difficulty_meowpow = "N/A"
            except Exception as e:
                print(f"Error fetching MeowPow difficulty: {e}")
                difficulty_meowpow = "N/A"

            try:
                difficulty_script = await make_rpc_call(session, "getdifficulty", [1])
                if difficulty_script is None:
                    difficulty_script = "N/A"
            except Exception as e:
                print(f"Error fetching Script difficulty: {e}")
                difficulty_script = "N/A"

            # Get hashrate values using RPC
            try:
                hashrate_meowpow = await make_rpc_call(session, "getnetworkhashps", [0, -1, "meowpow"])
                if hashrate_meowpow is not None:
                    hashrate_meowpow = hashrate_meowpow / 1e9  # Convert to GH/s
                else:
                    hashrate_meowpow = "N/A"
            except Exception as e:
                print(f"Error fetching MeowPow hashrate: {e}")
                hashrate_meowpow = "N/A"

            try:
                hashrate_script = await make_rpc_call(session, "getnetworkhashps", [0, -1, "scrypt"])
                if hashrate_script is not None:
                    hashrate_script = hashrate_script / 1e9  # Convert to GH/s
                else:
                    hashrate_script = "N/A"
            except Exception as e:
                print(f"Error fetching Script hashrate: {e}")
                hashrate_script = "N/A"

            # Get block count using RPC
            try:
                block_count = await make_rpc_call(session, "getblockcount", [])
                if block_count is None:
                    block_count = "N/A"
            except Exception as e:
                print(f"Error fetching block count: {e}")
                block_count = "N/A"

            # Keep using the old endpoint for supply (no replacement available yet)
            try:
                async with session.get("https://mewc.cryptoscope.io/api/getcoinsupply") as response:
                    supply_data = await response.json()
                    supply = float(supply_data["coinsupply"]) / 1_000_000_000  # Already in billions
            except Exception:
                supply = "N/A"

            # --- COINGECKO DATA COLLECTION ---
            try:
                async with session.get("https://api.coingecko.com/api/v3/coins/meowcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false") as response:
                    coingecko_data = await response.json()
                    
                    # Extract price in USD
                    current_price = coingecko_data["market_data"]["current_price"]["usd"]
                    
                    # Extract 24h volume in USD
                    volume_24h = coingecko_data["market_data"]["total_volume"]["usd"]
                    
                    # Extract market cap in USD
                    market_cap_usd = coingecko_data["market_data"]["market_cap"]["usd"]
                    
                    # Extract 24h price change percentage
                    price_change_24h = coingecko_data["market_data"]["price_change_percentage_24h"]
                    
                    # Format price display with 24h change
                    if price_change_24h is not None:
                        if price_change_24h >= 0:
                            price_display = f"${current_price:.6f} (▲ +{price_change_24h:.2f}% 24h)"
                        else:
                            price_display = f"${current_price:.6f} (▼ {price_change_24h:.2f}% 24h)"
                    else:
                        price_display = f"${current_price:.6f}"
                        
                    print("\nCoinGecko data retrieved:")
                    print(f"Price: ${current_price:.6f}")
                    print(f"24h Volume: ${volume_24h:,.2f}")
                    print(f"Market Cap: ${market_cap_usd:,.0f}")
                    print(f"24h Change: {price_change_24h:.2f}%\n")
                    
            except Exception as e:
                print(f"Error fetching CoinGecko data: {e}")
                current_price = "N/A"
                volume_24h = "N/A"
                market_cap_usd = "N/A"
                price_display = "N/A"

        try:
            member_count = guild.member_count
        except Exception:
            member_count = "N/A"

        # Define the category name for statistics channels
        category_name = "Meowcoin Server Stats"
        category = discord.utils.get(guild.categories, name=category_name)

        if not category:
            print(f"Creating category '{category_name}'")
            category = await guild.create_category(category_name)

        time.sleep(0.5)

        # Update or create individual statistics channels
        print(f"Members '{member_count}'")
        await create_or_update_channel(guild, category, "Members:", member_count)
        time.sleep(0.5)
        print(f"Difficulty MeowPow '{difficulty_meowpow}'")
        await create_or_update_channel(guild, category, "Difficulty (MeowPow):", difficulty_meowpow)
        time.sleep(0.5)
        print(f"Difficulty Script '{difficulty_script}'")
        await create_or_update_channel(guild, category, "Difficulty (Script):", difficulty_script)
        time.sleep(0.5)
        print(f"Hashrate MeowPow '{hashrate_meowpow}'")
        await create_or_update_channel(guild, category, "Hashrate (MeowPow): GH/s", hashrate_meowpow)
        time.sleep(0.5)
        print(f"Hashrate Script '{hashrate_script}'")
        await create_or_update_channel(guild, category, "Hashrate (Script): GH/s", hashrate_script)
        time.sleep(0.5)
        print(f"Block '{block_count}'")
        await create_or_update_channel(guild, category, "Block:", block_count)
        time.sleep(0.5)
        print(f"Supply '{supply}'")
        await create_or_update_channel(guild, category, "Supply:", supply)
        time.sleep(0.5)
        print(f"Price '{price_display}'")
        await create_or_update_channel(guild, category, "Price:", price_display)
        time.sleep(0.5)
        # Ensure volume is formatted correctly
        if volume_24h != "N/A":
            formatted_volume = "{:,.0f}".format(volume_24h)
        else:
            formatted_volume = "N/A"
        print(f"24h Volume '{formatted_volume}'")
        await create_or_update_channel(guild, category, "24h Volume: $", formatted_volume)
        time.sleep(0.5)
        # Use market cap directly from CoinGecko
        if market_cap_usd != "N/A":
            formatted_market_cap = "{:,.0f}".format(market_cap_usd)
        else:
            formatted_market_cap = "N/A"
        print(f"Market Cap '{formatted_market_cap}'")
        await create_or_update_channel(guild, category, "Market Cap: $", formatted_market_cap)
        time.sleep(0.5)
        # Set all channels to private
        for channel in category.voice_channels:
            await set_channel_private(category, channel)

    except Exception as e:
        print(f"An error occurred while updating channels: {e}")

# Define a task to update statistics channels every 5 minutes
@tasks.loop(minutes=5)
async def update_stats_task():
    for guild in client.guilds:
        print(f"Updating stats for guild '{guild.name}'")
        await update_stats_channels(guild)

@client.event
async def on_ready():
    print("The bot is ready")
    update_stats_task.start()

# Run the bot with the provided token
client.run(TOKEN)
