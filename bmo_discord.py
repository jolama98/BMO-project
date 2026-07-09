import discord
import asyncio
import threading
import random
import logging
import traceback


def log_info(msg):
    print(msg, flush=True)
    logging.info(msg)


def log_error(msg, error=None):
    print(msg, flush=True)
    logging.error(msg)
    if error:
        logging.error(traceback.format_exc())


class BMODiscordBot:
    def __init__(self, token, user_id, bmo_brain, discord_queue):
        self.token = token
        self.user_id = user_id
        self.bmo_brain = bmo_brain
        self.discord_queue = discord_queue

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.loop = None
        self.dm_channel = None

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    async def on_ready(self):
        try:
            log_info(f"[DISCORD READY] Connected as {self.client.user}")
            user = await self.client.fetch_user(self.user_id)
            self.dm_channel = await user.create_dm()
            await self.dm_channel.send("BMO is online! (¬‿¬)")
            log_info("[DISCORD OUT] BMO is online message sent")
            asyncio.create_task(self.random_thought_loop())
        except Exception as e:
            log_error("[DISCORD ERROR] on_ready failed", e)

    async def on_message(self, message):
        try:
            if message.author == self.client.user:
                return

            if isinstance(message.channel, discord.DMChannel):
                log_info(f"[USER IN] {message.content}")

                if message.content.startswith("!prompt"):
                    new_instruction = message.content[7:].strip()
                    if new_instruction:
                        self.discord_queue.put({
                            "source": "prompt_update",
                            "content": new_instruction
                        })
                        if self.dm_channel is not None:
                            await self.dm_channel.send("BMO updated! 🌱")
                            log_info("[DISCORD OUT] Prompt update confirmed")
                        log_info("[DISCORD OUT] Prompt update confirmed")
                    else:
                        if self.dm_channel is not None:
                            await self.dm_channel.send("BMO needs something after !prompt, friend.")
                            log_info("[DISCORD OUT] Empty prompt warning sent")
                    return

                self.discord_queue.put({
                    "source": "discord",
                    "content": message.content
                })

                log_info(
                    f"[QUEUE] Message added. Queue size: {self.discord_queue.qsize()}")

        except Exception as e:
            log_error("[DISCORD ERROR] on_message failed", e)

    async def random_thought_loop(self):
        while True:
            try:
                wait_seconds = random.randint(3600, 14400)
                log_info(f"[RANDOM LOOP] Sleeping for {wait_seconds} seconds")
                await asyncio.sleep(wait_seconds)

                if self.dm_channel is None:
                    log_info("[RANDOM LOOP] No DM channel yet")
                    continue

                log_info("[RANDOM LOOP] Generating random thought")
                thought = await asyncio.get_event_loop().run_in_executor(
                    None, self.bmo_brain
                )

                log_info(f"[BMO RANDOM OUT] {thought}")
                await self.dm_channel.send(thought)

            except Exception as e:
                log_error("[DISCORD ERROR] random_thought_loop failed", e)
                await asyncio.sleep(30)

    def send_message(self, text):
        if self.dm_channel and self.loop:
            log_info(f"[DISCORD SEND REQUEST] {text}")
            future = asyncio.run_coroutine_threadsafe(
                self.dm_channel.send(text),
                self.loop
            )

            def done_callback(f):
                try:
                    f.result()
                    log_info("[DISCORD SEND SUCCESS]")
                except Exception as e:
                    log_error("[DISCORD SEND FAILED]", e)

            future.add_done_callback(done_callback)
        else:
            log_error("[DISCORD SEND FAILED] No DM channel or event loop")

    def run_in_thread(self):
        def _run():
            try:
                log_info("[DISCORD THREAD] Starting Discord event loop")
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
                self.loop.run_until_complete(self.client.start(self.token))
            except Exception as e:
                log_error("[DISCORD THREAD ERROR] Discord client crashed", e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
