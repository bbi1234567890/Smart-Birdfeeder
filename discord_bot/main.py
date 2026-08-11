import json
import discord
from discord.ext import commands
import paho.mqtt.client as mqtt
import time
import subprocess
import asyncio

MQTT_CLIENT_ID = "pi_server"
MQTT_BROKER = "localhost"
ESP32_STATUS = "birdfeeder/esp32/status"
ESP32_COMMANDS = "birdfeeder/esp32/commands"
PI_STATUS = "birdfeeder/pi/status"
PI_COMMANDS = "birdfeeder/pi/commands"

COMMANDS = {
    "on": {
        "description": "Turn pi on.",
        "payload": "on",
        "sending_msg": "Sending on command...",
        "success_msg": "Pi turned on by ESP32.",
        "timeout_msg": "On command timed out. Please try again later.",
    },
    "off": {
        "description": "Turn pi off.",
        "payload": "off",
        "sending_msg": "Sending off command...",
        "success_msg": "Pi turned off by ESP32.",
        "timeout_msg": "Off command timed out. Please try again later.",
    },
    "exit": {
        "description": "Exit the pi python script.",
        "payload": "exit",
        "sending_msg": "Sending exit command...",
        "success_msg": "Pi exited python script.",
        "timeout_msg": "Exit command timed out. Please try again later.",
    },
    "restart_pi": {
        "description": "Restart the pi.",
        "payload": "restart_pi",
        "sending_msg": "Sending restart command...",
        "success_msg": "Pi has restarted.",
        "timeout_msg": "Restart command timed out. Please try again later.",
    },
    "restart_esp32": {
        "description": "Restart the ESP32.",
        "payload": "restart_esp32",
        "sending_msg": "Sending restart command...",
        "success_msg": "ESP32 has restarted.",
        "timeout_msg": "Restart command timed out. Please try again later.",
    },
}

with open("configuration.json", "r") as config: 
	data = json.load(config)
	token = data["token"]
	prefix = data["prefix"]
	owner_id = 836754662504923207
	ssid = data["ssid"]
	pwd = data["pwd"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=prefix, description="birdfeeder bot", intents=intents)
shutdown = False
loop = None

def connect_mqtt():
    while not client.is_connected():
        try:
            client.connect(MQTT_BROKER, 1883, 60)
            client.loop_start()
            time.sleep(1)
            if not client.is_connected():
                print("Failed to connect to MQTT broker.")
                time.sleep(5)
        except Exception as e:
            print("Error connecting to MQTT broker:", e)
            time.sleep(5)

def on_mqtt_message(client, userdata, message):
    print(f"Received message on topic {message.topic}: {message.payload.decode()}")
    if message.topic == ESP32_STATUS and message.payload.decode() == "streamReceived":
        print("Received stream request confirmation from ESP32.")
        loop.call_soon_threadsafe(bot.stream_confirmation_event.set())
    if message.topic == ESP32_STATUS and message.payload.decode() == "pi on":
        print("Received pi on confirmation from ESP32.")
        loop.call_soon_threadsafe(bot.on_confirmation_event.set())
    if message.topic == ESP32_STATUS and message.payload.decode() == "pi off":
        print("Received pi off confirmation from ESP32.")
        loop.call_soon_threadsafe(bot.off_confirmation_event.set())
    if message.topic == ESP32_STATUS and message.payload.decode() == "exitSignalReceived":
        print("Received exit confirmation from ESP32.")
        loop.call_soon_threadsafe(bot.exit_confirmation_event.set())
    if message.topic == ESP32_STATUS and message.payload.decode() == "restartPiSignalReceived":
        print("Received restart pi confirmation from ESP32.")
        loop.call_soon_threadsafe(bot.restart_pi_confirmation_event.set())
    if message.topic == ESP32_STATUS and message.payload.decode() == "restartESP32SignalReceived":
        print("Received restart esp32 confirmation from ESP32.")
        loop.call_soon_threadsafe(bot.restart_esp32_confirmation_event.set())
    if message.topic == PI_STATUS:
        print("Received stream URL from Pi: ", message.payload.decode())
        bot.stream_url = message.payload.decode()
        loop.call_soon_threadsafe(bot.stream_url_event.set())

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker.")
        client.subscribe(PI_STATUS)
        client.subscribe(ESP32_STATUS)
        client.subscribe(ESP32_COMMANDS)
        client.subscribe(PI_COMMANDS)
    else:
        print(f"Failed to connect to MQTT broker. Return code: {rc}")

def on_disconnect(client, userdata, rc):
    print(f"Disconnected: {rc}")
    while not client.is_connected():
        try:
            client.reconnect()
        except Exception as e:
            print(f"Reconnect attempt failed: {e}")
            time.sleep(5)

async def run_confirmed_command(
    interaction: discord.Interaction,
    cmd_key: str,
    timeout: float = 90,
) -> None:

    cfg = COMMANDS[cmd_key]
    event = getattr(bot, f"{cmd_key}_confirmation_event")
 
    if interaction.user.id != owner_id:
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )
        return
 
    if not client.is_connected():
        await interaction.response.send_message(
            "MQTT client is not connected. Please try again later.", ephemeral=True
        )
        return
 
    print(f"{cmd_key} command sent.")
    event.clear()
    await interaction.response.send_message(cfg["sending_msg"])
 
    deadline = time.monotonic() + timeout
    while not event.is_set() and time.monotonic() < deadline:
        client.publish(ESP32_COMMANDS, cfg["payload"])
        await asyncio.sleep(1)
 
    if event.is_set():
        await interaction.followup.send(cfg["success_msg"], ephemeral=True)
    else:
        print(f"{cmd_key} command failed after {timeout} seconds.")
        await interaction.followup.send(cfg["timeout_msg"], ephemeral=True)
 
@bot.tree.command(name="on", description=COMMANDS["on"]["description"])
async def pi_on(interaction: discord.Interaction):
    await run_confirmed_command(interaction, "on")
 
 
@bot.tree.command(name="off", description=COMMANDS["off"]["description"])
async def pi_off(interaction: discord.Interaction):
    await run_confirmed_command(interaction, "off")
 
 
@bot.tree.command(name="exit", description=COMMANDS["exit"]["description"])
async def pi_exit(interaction: discord.Interaction):
    await run_confirmed_command(interaction, "exit")
 
 
@bot.tree.command(name="restart_pi", description=COMMANDS["restart_pi"]["description"])
async def restart_pi(interaction: discord.Interaction):
    await run_confirmed_command(interaction, "restart_pi")
 
 
@bot.tree.command(name="restart_esp32", description=COMMANDS["restart_esp32"]["description"])
async def restart_esp32(interaction: discord.Interaction):
    await run_confirmed_command(interaction, "restart_esp32")
    
@bot.tree.command(name="request_stream", description="Request birdfeeder stream.")
async def requestStream(interaction: discord.Interaction):
    global shutdown
    if not client.is_connected():
        await interaction.response.send_message("MQTT client is not connected. Please try again later.")
        return
    
    print("Stream requested.")
    bot.stream_confirmation_event.clear()
    bot.stream_url_event.clear()
    bot.stream_url = ""
    shutdown = False

    await interaction.response.send_message("Sending stream command...")
    
    before = time.monotonic()
    while not bot.stream_confirmation_event.is_set() and time.monotonic() - before < 90:
        client.publish(ESP32_COMMANDS, "stream")
        await asyncio.sleep(1)
    
    if bot.stream_confirmation_event.is_set():
        await interaction.followup.send("Stream request confirmed by ESP32. Waiting for stream URL...", ephemeral=True)
    else:
        await interaction.followup.send("Stream request timed out. Please try again later.", ephemeral=True)
        print("Stream request failed after 90 seconds.")
        return

    try:
        await asyncio.wait_for(bot.stream_url_event.wait(), timeout=90)
        await interaction.followup.send(f"Stream URL received. How long until shutdown?", view=TimeRequestedButton(), ephemeral=True)
        
    except asyncio.TimeoutError:
        await interaction.followup.send("Failed to receive stream URL. Please try again later.", ephemeral=True)
        print("Stream URL not received after 90 seconds.")
        return
    
@bot.tree.command(name="request_url", description="Request stream URL from Pi.")
async def requestURL(interaction: discord.Interaction):
    print("Stream URL requested. Sending stream URL...")
    if not bot.stream_confirmation_event.is_set():
        await interaction.response.send_message("Stream has not been requested or confirmed yet. Please request the stream first.", ephemeral=True)
        return
    await interaction.response.send_message(bot.stream_url, ephemeral=True)
    
    
class ShutdownButton(discord.ui.View):
    @discord.ui.button(label="Shutdown", style=discord.ButtonStyle.red)
    async def shutdown_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Shutting down feeder...", ephemeral=True)
        await shutdown_stream()
        
class TimeRequestedButton(discord.ui.View):
    @discord.ui.button(label="Set time", style=discord.ButtonStyle.green)
    async def set_time_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeRequested())



class TimeRequested(discord.ui.Modal, title="Shutdown Timer"):

    def __init__(self):
        super().__init__()
        self.time_input = discord.ui.TextInput(label="Enter time in minutes", placeholder="e.g. 30", required=True)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        global shutdown
        try:
            time_minutes = int(self.time_input.value)

            if time_minutes <= 0 or time_minutes >= 60:
                await interaction.response.send_message("Please enter a valid time greater than 0 and less than 60.", ephemeral=True)
                return

            await interaction.response.send_message(f"{bot.stream_url} Shutdown timer set for {time_minutes} minutes.", view=ShutdownButton(), ephemeral=True)
            print(f"Shutdown timer set for {time_minutes} minutes.")
            client.publish(PI_COMMANDS, str(time_minutes))
            time_stop = time.monotonic() + (time_minutes * 60)
            while time.monotonic() < time_stop:
                if shutdown:
                    return
                await asyncio.sleep(1)
            await interaction.followup.send("Shutdown timer completed. Shutting down feeder...", ephemeral=True)
            await shutdown_stream()
        except ValueError:
            await interaction.response.send_message("Invalid input. Please enter a number.", ephemeral=True)



async def shutdown_stream():
    global shutdown
    shutdown = True
    client.publish(PI_COMMANDS, "stop_stream")
    bot.stream_confirmation_event.clear()


@bot.event
async def on_ready():

    print(f"We have logged in as {bot.user}")
    print(discord.__version__)
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{bot.command_prefix}help"))
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands.")

async def main():
    global client, loop

    bot.stream_confirmation_event = asyncio.Event()
    bot.on_confirmation_event = asyncio.Event()
    bot.off_confirmation_event = asyncio.Event()
    bot.exit_confirmation_event = asyncio.Event()
    bot.restart_pi_confirmation_event = asyncio.Event()
    bot.restart_esp32_confirmation_event = asyncio.Event()
    bot.stream_url_event = asyncio.Event()
    bot.stream_url = ""

    loop = asyncio.get_running_loop()

    client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.message_callback_add(ESP32_STATUS, on_mqtt_message)
    client.message_callback_add(PI_STATUS, on_mqtt_message)

    await loop.run_in_executor(None, connect_mqtt)

    async with bot:
        await bot.start(token)


if __name__ == '__main__':
    asyncio.run(main())
