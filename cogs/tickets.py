import discord
from discord import app_commands
from discord.ext import commands
import datetime

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- 通常のチャットに反応する設定 ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.content == "チケット確認":
            try:
                res = self.bot.supabase.table("user_tickets").select("count").eq("user_id", str(message.author.id)).execute()
                ticket_count = res.data[0].get("count", 0) if res.data else 0
                await message.reply(f"🎟️ {message.author.mention} さんの所持チケット: **{ticket_count} 枚**")
            except Exception as e:
                print(f"Error fetching tickets via text: {e}")

    # --- スラッシュコマンド（従来通り） ---
    @app_commands.command(name="tickets", description="自分の所持チケット枚数を確認します")
    async def tickets(self, interaction: discord.Interaction):
        try:
            res = self.bot.supabase.table("user_tickets").select("count").eq("user_id", str(interaction.user.id)).execute()
            ticket_count = res.data[0].get("count", 0) if res.data else 0
            await interaction.response.send_message(f"🎟️ {interaction.user.mention} さんの所持チケット: **{ticket_count} 枚**")
        except Exception as e:
            print(f"Error fetching tickets: {e}")
            await interaction.response.send_message("❌ チケット枚数の取得に失敗しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tickets(bot))