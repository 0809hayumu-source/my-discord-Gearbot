import discord
from discord import app_commands
from discord.ext import commands
import datetime

class Coins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- 通常のチャットに反応する設定 ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # 「コイン確認」というメッセージに反応
        if message.content == "コイン確認":
            # 既存の読み込みメソッドを利用
            c = self.bot.load_data(message.author.id)
            await message.reply(f"🪙 {message.author.mention} さんの所持コイン: **{c} 枚**")

    # --- スラッシュコマンド（従来通り） ---
    @app_commands.command(name="coins", description="所持コインを確認します")
    async def coins(self, interaction: discord.Interaction):
        c = self.bot.load_data(interaction.user.id)
        await interaction.response.send_message(f"🪙 {interaction.user.mention} さんの所持コイン: **{c} 枚**")

async def setup(bot):
    await bot.add_cog(Coins(bot))