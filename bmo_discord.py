import asyncio
import logging
import random
import threading
import traceback

import discord


def log_info(msg):
    print(msg, flush=True)
    logging.info(msg)


def log_error(msg, error=None):
    print(msg, flush=True)
    logging.error(msg)

    if error:
        logging.error(traceback.format_exc())


class BMODiscordBot:
    def __init__(self, token, user_ids, bmo_brain, discord_queue):
        self.token = token
        self.user_ids = {int(uid.strip()) for uid in user_ids if uid.strip()}
        self.bmo_brain = bmo_brain
        self.discord_queue = discord_queue

        intents = discord.Intents.default()
        intents.message_content = True

        self.client = discord.Client(intents=intents)
        self.loop = None
        self.dm_channel = None

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    async def send_dm(self, text):
        if self.dm_channel is None:
            log_error("[DISCORD SEND FAILED] No DM channel")
            return False

        try:
            await self.dm_channel.send(text)
            log_info(f"[DISCORD OUT] {text}")
            return True

        except Exception as e:
            log_error("[DISCORD SEND FAILED]", e)
            return False

    async def on_ready(self):
        log_info(f"[DISCORD READY] Connected as {self.client.user}")
        log_info(f"[DISCORD USERS] Loaded IDs: {sorted(self.user_ids)}")

        self.dm_channels = {}

        for user_id in self.user_ids:
            try:
                log_info(f"[DISCORD USER] Opening DM for {user_id}")

                user = await self.client.fetch_user(user_id)
                dm_channel = await user.create_dm()

                self.dm_channels[user_id] = dm_channel

                await dm_channel.send("BMO is online! (¬‿¬)")
                log_info(f"[DISCORD OUT] Online message sent to {user_id}")

            except Exception as e:
                log_error(
                    f"[DISCORD USER ERROR] Could not open DM for {user_id}",
                    e,
                )

        if self.dm_channels:
            asyncio.create_task(self.random_thought_loop())
        else:
            log_error("[DISCORD ERROR] No valid DM channels were created")

    async def on_message(self, message):
        try:
            if message.author == self.client.user:
                return

            if not isinstance(message.channel, discord.DMChannel):
                return

            log_info(f"[USER IN] {message.content}")

            if message.content.startswith("!prompt"):
                new_instruction = message.content[7:].strip()

                if new_instruction:
                    self.discord_queue.put(
                        {
                            "source": "prompt_update",
                            "content": new_instruction,
                        }
                    )

                    await self.send_dm("BMO updated! 🌱")

                else:
                    await self.send_dm("BMO needs something after !prompt, friend.")

                return

            self.discord_queue.put(
                {
                    "source": "discord",
                    "content": message.content,
                }
            )

            log_info(
                f"[QUEUE] Message added. Queue size: " f"{self.discord_queue.qsize()}"
            )

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

                running_loop = asyncio.get_running_loop()

                thought = await running_loop.run_in_executor(
                    None,
                    self.bmo_brain,
                )

                if thought and thought.strip():
                    log_info(f"[BMO RANDOM OUT] {thought}")
                    await self.send_dm(thought)

            except Exception as e:
                log_error(
                    "[DISCORD ERROR] random_thought_loop failed",
                    e,
                )

                await asyncio.sleep(30)

    def send_message(self, text):
        if self.dm_channel is None or self.loop is None:
            log_error("[DISCORD SEND FAILED] No DM channel or event loop")
            return

        log_info(f"[DISCORD SEND REQUEST] {text}")

        future = asyncio.run_coroutine_threadsafe(
            self.send_dm(text),
            self.loop,
        )

        def done_callback(completed_future):
            try:
                success = completed_future.result()

                if success:
                    log_info("[DISCORD SEND SUCCESS]")

            except Exception as e:
                log_error("[DISCORD SEND FAILED]", e)

        future.add_done_callback(done_callback)

    def run_in_thread(self):
        def _run():
            try:
                log_info("[DISCORD THREAD] Starting Discord event loop")

                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

                self.loop.run_until_complete(self.client.start(self.token))

            except Exception as e:
                log_error(
                    "[DISCORD THREAD ERROR] Discord client crashed",
                    e,
                )

        thread = threading.Thread(
            target=_run,
            daemon=True,
        )

        thread.start()
