import discord
from discord import app_commands
from discord.ext import commands
from utils import process_rank_system

class RankCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. スラッシュコマンド /rank
    @app_commands.command(name="rank", description="現在のランクと進捗を確認します")
    async def rank_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # 金額 0 で呼び出すことで、コインを減らさずに現在の状況だけ取得する
        rank_embed = await process_rank_system(self.bot, interaction.user.id, 0)
        await interaction.followup.send(embed=rank_embed, ephemeral=True)

    # 2. 指定チャンネルでのメッセージ反応「ランク確認」
    @commands.Cog.listener()
    async def on_message(self, message):
        # ボットのメッセージは無視
        if message.author.bot:
            return
        
        # 指定されたチャンネルIDのみ反応
        TARGET_CHANNEL_ID = 1502492777324347562
        if message.channel.id != TARGET_CHANNEL_ID:
            return

        if message.content == "ランク確認":
            # 金額 0 で呼び出して現在の状況を取得
            rank_embed = await process_rank_system(self.bot, message.author.id, 0)
            await message.reply(embed=rank_embed)

async def setup(bot):
    await bot.add_cog(RankCog(bot))