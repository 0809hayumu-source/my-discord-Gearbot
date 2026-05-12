import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import random
from utils import process_rank_system

# --- ガチャ実行処理 (中身は変更なし) ---
async def execute_gacha_logic(bot, target, count, user, current_total_tickets, is_coin=False):
    results_text = []
    total_won_tickets = 0
    is_jackpot = False

    for i in range(count):
        win_count = random.choices([0, 1, 2, 3, 10], weights=[70.0, 27.0, 2.0, 0.9, 0.1], k=1)[0]
        total_won_tickets += win_count
        prefix = f"`{i+1:02d}回目`: "
        if win_count == 0:
            results_text.append(f"{prefix}× はずれ")
        elif win_count == 10:
            results_text.append(f"{prefix}✨ **ぶち抜き (10枚)** ✨")
            is_jackpot = True
        else:
            results_text.append(f"{prefix}🎟️ **{win_count}枚**")

    new_total_tickets = current_total_tickets + total_won_tickets
    bot.supabase.table("user_tickets").upsert({"user_id": str(user.id), "count": new_total_tickets}).execute()

    embed = discord.Embed(title="🎰 ガチャ結果発表！！", color=0xFFD700 if is_jackpot else 0x3498DB)
    embed.description = "\n".join(results_text)
    embed.add_field(name="🎁 今回の獲得", value=f"**{total_won_tickets} 枚**", inline=True)
    embed.add_field(name="📊 累計所持", value=f"**{new_total_tickets} 枚**", inline=True)
    
    if is_jackpot:
        embed.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHJmZzRyeXN6eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4JmVwPXYxX2ludGVybmFsX2dpZl9ieV9pZCZjdD1n/26tOZ42Mg6pbMubHW/giphy.gif")
    
    content = f"{user.mention} さんの抽選が完了しました！"
    if is_coin:
        await target.send(content=content, embed=embed)
    else:
        await target.followup.send(content=content, embed=embed)

# --- 1. コインガチャ最終確認View ---
class CoinGachaConfirmView(View):
    def __init__(self, bot=None, cost=None, count=None):
        super().__init__(timeout=None) # 永続化
        self.bot, self.cost, self.count = bot, cost, count

    @discord.ui.button(label="本当に回す", style=discord.ButtonStyle.danger, custom_id="gacha_confirm_yes")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        res_coin = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(interaction.user.id)).execute()
        current_coins = res_coin.data[0].get("coin_count", 0) if res_coin.data else 0

        if current_coins < self.cost:
            return await interaction.followup.send("❌ コインが足りません。", ephemeral=True)
        
        rank_embed = await process_rank_system(self.bot, interaction.user.id, self.cost)
        
        res_ticket = self.bot.supabase.table("user_tickets").select("count").eq("user_id", str(interaction.user.id)).execute()
        current_tickets = res_ticket.data[0].get("count", 0) if res_ticket.data else 0
        
        log_channel = self.bot.get_channel(1498675526653710366)
        
        if log_channel:
            await execute_gacha_logic(self.bot, log_channel, self.count, interaction.user, current_tickets, is_coin=True)
            await interaction.edit_original_response(content=f"✅ 完了！ {log_channel.mention} を確認してください。", view=None)
            await interaction.followup.send(embed=rank_embed, ephemeral=True)
        else:
            await execute_gacha_logic(self.bot, interaction, self.count, interaction.user, current_tickets, is_coin=False)
            await interaction.followup.send(embed=rank_embed, ephemeral=True)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary, custom_id="gacha_confirm_no")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ キャンセルしました。", view=None)

# --- 2. 承認後の実行ボタン (PayPay用) ---
class GachaExecuteView(View):
    def __init__(self, bot=None, count=None, user=None):
        super().__init__(timeout=None)
        self.bot, self.count, self.user = bot, count, user

    @discord.ui.button(label="🔥 ガチャを回す", style=discord.ButtonStyle.danger, emoji="🎰", custom_id="gacha_execute_btn")
    async def execute(self, interaction: discord.Interaction, button: Button):
        if self.user and interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ 本人のみ可能です。", ephemeral=True)
        
        await interaction.response.defer()
        res = self.bot.supabase.table("user_tickets").select("count").eq("user_id", str(interaction.user.id)).execute()
        current_tickets = res.data[0].get("count", 0) if res.data else 0
        await execute_gacha_logic(self.bot, interaction, self.count, interaction.user, current_tickets, is_coin=False)
        await interaction.edit_original_response(content="✅ ガチャを回しました。", view=None)

# --- 3. 管理者承認View ---
class AdminGachaVerifyView(View):
    def __init__(self, bot=None, count=None, user=None):
        super().__init__(timeout=None)
        self.bot, self.count, self.user = bot, count, user

    @discord.ui.button(label="【管理者用】承認", style=discord.ButtonStyle.danger, custom_id="admin_gacha_verify_btn")
    async def verify(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
        await interaction.response.edit_message(content=f"✅ 承認完了！", view=None)
        await interaction.channel.send(content=f"🎰 {self.user.mention if self.user else 'ユーザー'} さん、どうぞ！", view=GachaExecuteView(self.bot, self.count, self.user))

# --- 4. PayPay申請モーダル (変更なし) ---
class GachaPayPayModal(Modal):
    def __init__(self, bot, price, count):
        super().__init__(title=f"ガチャチケット購入 ({price}円)")
        self.bot, self.price, self.count = bot, price, count
        self.link = TextInput(label='PayPayリンク', placeholder="https://paypay.me/...", required=True)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="支払管理ログ・ガチャログ")
        channel = await guild.create_text_channel(name=f"ガチャ申請-{interaction.user.name}", category=category)
        
        embed = discord.Embed(title="🎰 ガチャチケット申請(PayPay)", color=0x3498DB)
        embed.add_field(name="申請者", value=interaction.user.mention, inline=True)
        embed.add_field(name="金額 / 回数", value=f"{self.price}円 / {self.count}連", inline=True)
        embed.add_field(name="🔗 PayPayリンク", value=self.link.value, inline=False)
        
        await channel.send(embed=embed, view=AdminGachaVerifyView(self.bot, self.count, interaction.user))
        await interaction.followup.send(f"✅ 申請完了。 {channel.mention} へどうぞ。", ephemeral=True)

# --- 5. メインメニュー用View ---
class GachaMenuView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

        # PayPayボタン
        paypay_data = [(500, 5), (800, 10)]
        for p, c in paypay_data:
            btn = Button(label=f"💴 PayPay {c}連({p}円)", style=discord.ButtonStyle.success, custom_id=f"gacha_paypay_{p}")
            btn.callback = self.make_paypay_callback(p, c)
            self.add_item(btn)

        # コインボタン
        coin_data = [(600, 5), (1000, 10)]
        for cost, c in coin_data:
            btn = Button(label=f"🪙 コイン {c}連({cost}枚)", style=discord.ButtonStyle.primary, custom_id=f"gacha_coin_{cost}")
            btn.callback = self.make_coin_callback(cost, c)
            self.add_item(btn)

    def make_paypay_callback(self, p, c):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_modal(GachaPayPayModal(self.bot, p, c))
        return callback

    def make_coin_callback(self, cost, c):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_message(
                f"📢 コイン **{cost}枚** を消費して **{c}連ガチャ** を回します。本当によろしいですか？", 
                view=CoinGachaConfirmView(self.bot, cost, c), 
                ephemeral=True
            )
        return callback

# --- メインメニューCog ---
class Gacha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gacha", description="ガチャメニューを表示します")
    async def gacha_menu(self, interaction: discord.Interaction):
        await interaction.response.send_message("⌛ ガチャメニューを読み込んでいます...", ephemeral=False)
        
        embed = discord.Embed(title="🎰 ガチャメニュー", description="PayPayまたはコインで回せます！", color=0x3498DB)
        await interaction.edit_original_response(content=None, embed=embed, view=GachaMenuView(self.bot))

async def setup(bot):
    await bot.add_cog(Gacha(bot))