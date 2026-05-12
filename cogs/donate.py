import discord
from discord import app_commands, ui
from discord.ext import commands

# --- 設定 ---
LOG_CHANNEL_ID = 1503673651373936660  # 送っていただいたログチャンネルID

# ==========================================
# 1. 寄付ボタンの処理 (Viewクラス)
# ==========================================
class DonatePanelView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="100コイン寄付", style=discord.ButtonStyle.green, emoji="💰", custom_id="donate_100")
    async def donate_100(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_donation(interaction, 100)

    @ui.button(label="500コイン寄付", style=discord.ButtonStyle.primary, emoji="💎", custom_id="donate_500")
    async def donate_500(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_donation(interaction, 500)

    @ui.button(label="1000コイン寄付", style=discord.ButtonStyle.danger, emoji="🔥", custom_id="donate_1000")
    async def donate_1000(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_donation(interaction, 1000)

    async def process_donation(self, interaction: discord.Interaction, amount: int):
        user_id = str(interaction.user.id)
        
        try:
            # 1. 現在の所持金を確認
            res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", user_id).execute()
            current_coins = res.data[0].get("coin_count", 0) if (res.data and len(res.data) > 0) else 0

            if current_coins < amount:
                return await interaction.response.send_message(f"❌ コインが足りません！（所持: {current_coins}コイン）", ephemeral=True)

            # 2. コインを減らす
            new_balance = current_coins - amount
            self.bot.supabase.table("user_coins").update({"coin_count": new_balance}).eq("user_id", user_id).execute()

            # 3. ログチャンネルへ通知を送信
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="💖 寄付ログ",
                    description=f"{interaction.user.mention} 様から寄付がありました！",
                    color=discord.Color.brand_red()
                )
                log_embed.add_field(name="寄付額", value=f"**{amount} コイン**", inline=True)
                log_embed.add_field(name="新残高", value=f"{new_balance} コイン", inline=True)
                log_embed.set_footer(text=f"User ID: {user_id}")
                await log_channel.send(embed=log_embed)

            # 4. 本人への通知
            await interaction.response.send_message(
                f"💖 **{amount}コイン** の寄付ありがとうございます！\n現在の残高: **{new_balance}コイン**", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(f"⚠️ エラーが発生しました: {e}", ephemeral=True)

# ==========================================
# 2. パネル設置コマンド (Cogクラス)
# ==========================================
class DonateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_donate_panel", description="寄付受付パネルを設置します")
    async def setup_donate_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者のみ実行可能です。", ephemeral=True)

        embed = discord.Embed(
            title="🎁 サーバーへの寄付・応援",
            description=(
                "いつもご利用いただきありがとうございます！\n"
                "いただいた寄付は、サーバー運営に大切に活用させていただきます。\n\n"
                "**【寄付の方法】**\n"
                "下のボタンを押すと、所持コインから寄付されます。"
            ),
            color=discord.Color.gold()
        )
        
        await interaction.channel.send(embed=embed, view=DonatePanelView(self.bot))
        await interaction.response.send_message("✅ 寄付パネルを設置しました！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(DonateCog(bot))