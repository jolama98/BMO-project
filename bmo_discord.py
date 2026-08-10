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
        logging.error("%s\n%s", error, traceback.format_exc())


class BMODiscordBot:
    def __init__(self, token, user_ids, bmo_brain, discord_queue):
        self.token = token
        self.user_ids = {int(str(uid).strip()) for uid in user_ids if str(uid).strip()}
        self.bmo_brain = bmo_brain
        self.discord_queue = discord_queue

        self.loop = None
        self.dm_channels = {}
        self.random_thought_task = None

        intents = discord.Intents.default()
        intents.message_content = True

        self.client = discord.Client(intents=intents)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    async def get_dm_channel(self, user_id):
        user_id = int(user_id)

        existing = self.dm_channels.get(user_id)
        if existing is not None:
            return existing

        try:
            log_info(f"[DISCORD USER] Opening DM for {user_id}")
            user = await self.client.fetch_user(user_id)
            dm_channel = await user.create_dm()
            self.dm_channels[user_id] = dm_channel
            return dm_channel
        except Exception as e:
            log_error(f"[DISCORD USER ERROR] Could not open DM for {user_id}", e)
            return None

    async def send_dm(self, user_id, text):
        user_id = int(user_id)

        if user_id not in self.user_ids:
            log_error(f"[DISCORD SEND FAILED] Unauthorized user ID: {user_id}")
            return False

        dm_channel = await self.get_dm_channel(user_id)
        if dm_channel is None:
            return False

        try:
            await dm_channel.send(text)
            log_info(f"[DISCORD OUT] Message sent to {user_id}")
            return True
        except Exception as e:
            log_error(f"[DISCORD SEND FAILED] Could not send to {user_id}", e)
            return False

    async def on_ready(self):
        log_info(f"[DISCORD READY] Connected as {self.client.user}")
        log_info(f"[DISCORD USERS] Loaded IDs: {sorted(self.user_ids)}")

        for user_id in self.user_ids:
            dm_channel = await self.get_dm_channel(user_id)
            if dm_channel is None:
                continue

            try:
                await dm_channel.send("BMO is online! (¬‿¬)")
                log_info(f"[DISCORD OUT] Online message sent to {user_id}")
            except Exception as e:
                log_error(f"[DISCORD USER ERROR] Could not message {user_id}", e)

        if self.random_thought_task is None or self.random_thought_task.done():
            self.random_thought_task = asyncio.create_task(self.random_thought_loop())

    async def on_message(self, message):
        try:
            if message.author == self.client.user:
                return

            if not isinstance(message.channel, discord.DMChannel):
                return

            user_id = int(message.author.id)
            if user_id not in self.user_ids:
                log_info(
                    f"[DISCORD BLOCKED] Unauthorized user {message.author} ({user_id})"
                )
                return

            content = message.content.strip()
            if not content:
                return

            log_info(f"[USER IN] User {user_id}: {content}")

            if content.lower().startswith("!prompt"):
                _, _, new_instruction = content.partition(" ")
                new_instruction = new_instruction.strip()

                if new_instruction:
                    self.discord_queue.put(
                        {
                            "source": "prompt_update",
                            "user_id": user_id,
                            "content": new_instruction,
                        }
                    )
                    await self.send_dm(user_id, "BMO updated! 🌱")
                else:
                    await self.send_dm(
                        user_id, "BMO needs something after !prompt, friend."
                    )
                return

            self.discord_queue.put(
                {
                    "source": "discord",
                    "user_id": user_id,
                    "username": str(message.author),
                    "content": content,
                }
            )

            log_info(
                f"[QUEUE] Message from {user_id} added. "
                f"Queue size: {self.discord_queue.qsize()}"
            )
        except Exception as e:
            log_error("[DISCORD ERROR] on_message failed", e)

    async def random_thought_loop(self):
        while not self.client.is_closed():
            try:
                wait_seconds = random.randint(3600, 14400)
                log_info(f"[RANDOM LOOP] Sleeping for {wait_seconds} seconds")
                await asyncio.sleep(wait_seconds)

                running_loop = asyncio.get_running_loop()

                for user_id in self.user_ids:
                    try:
                        thought = await running_loop.run_in_executor(
                            None,
                            self.bmo_brain,
                            user_id,
                        )
                        if thought and thought.strip():
                            log_info(f"[BMO RANDOM OUT] User {user_id}: {thought}")
                            await self.send_dm(user_id, thought)
                    except Exception as e:
                        log_error(f"[RANDOM ERROR] Thought failed for {user_id}", e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log_error("[DISCORD ERROR] random_thought_loop failed", e)
                await asyncio.sleep(30)

    def send_message(self, user_id, text):
        if self.loop is None or not self.loop.is_running():
            log_error("[DISCORD SEND FAILED] Discord event loop is not running")
            return False

        user_id = int(user_id)
        future = asyncio.run_coroutine_threadsafe(
            self.send_dm(user_id, text),
            self.loop,
        )

        def done_callback(completed_future):
            try:
                success = completed_future.result()
                if success:
                    log_info(f"[DISCORD SEND SUCCESS] User {user_id}")
                else:
                    log_error(f"[DISCORD SEND FAILED] User {user_id}")
            except Exception as e:
                log_error(f"[DISCORD SEND FAILED] User {user_id}", e)

        future.add_done_callback(done_callback)
        return True

    def run_in_thread(self):
        def _run():
            try:
                log_info("[DISCORD THREAD] Starting Discord event loop")
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
                self.loop.run_until_complete(self.client.start(self.token))
            except Exception as e:
                log_error("[DISCORD THREAD ERROR] Discord client crashed", e)
            finally:
                if self.loop and not self.loop.is_closed():
                    self.loop.close()
                log_info("[DISCORD THREAD] Event loop stopped")

        thread = threading.Thread(target=_run, name="BMO-Discord", daemon=True)
        thread.start()
        return thread
