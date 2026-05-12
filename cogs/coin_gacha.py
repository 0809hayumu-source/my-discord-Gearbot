import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random
import asyncio
from utils import process_rank_system

# --- コインガチャ実行View ---
class CoinGachaView(View):
    def __init__(self, bot, item):
        super().__init__(timeout=None) # 永続化のためにtimeoutはNone
        self.bot = bot
        self.item = item

    async def execute_rolls(self, interaction: discord.Interaction, count: int):
        user_id = str(interaction.user.id)
        price_per_roll = self.item['price']
        win_coins = self.item['win_coins']
        total_price = price_per_roll * count
        
        # 1. 支払い可能かチェック
        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", user_id).execute()
        current_coins = res.data[0].get("coin_count", 0) if res.data else 0
        
        if current_coins < total_price:
            return await interaction.response.send_message(f"❌ コイン不足 (必要: {total_price}枚 / 所持: {current_coins}枚)", ephemeral=True)

        # 2. 処理開始
        await interaction.response.defer(ephemeral=True)
        
        # 3. ランク・コイン一括更新（ここでの更新はランクアップ用）
        rank_embed = await process_rank_system(self.bot, interaction.user.id, total_price)
        
        # 4. 抽選処理
        actual_win_rate = float(self.item.get('max_slots', 50))
        gacha_name = self.item.get('name', "不明なガチャ")
        
        results_list = []
        hit_count = 0
        
        for i in range(count):
            if random.uniform(0, 100) < actual_win_rate:
                hit_count += 1
                results_list.append(f"`{i+1:02d}回目`: ✨ **当選！** (+{win_coins}枚)")
            else:
                results_list.append(f"`{i+1:02d}回目`: × はずれ")

        # 5. 当選金の加算
        total_won = hit_count * win_coins
        if total_won > 0:
            # 支払い後の最新残高を取得して加算
            res_after = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", user_id).execute()
            coins_now = res_after.data[0]['coin_count'] if res_after.data else 0
            
            self.bot.supabase.table("user_coins").update({
                "coin_count": coins_now + total_won
            }).eq("user_id", user_id).execute()

        # 6. 演出と結果表示
        await interaction.followup.send(f"🎰 「{gacha_name}」 {count}連ガチャを回しています...", ephemeral=True)
        await asyncio.sleep(1.2)

        # 結果Embed
        result_embed = discord.Embed(
            title=f"🎰 {gacha_name} 結果 ({count}連)",
            description="\n".join(results_list),
            color=0xFFD700 if hit_count > 0 else 0x95A5A6
        )
        summary = f"獲得合計: **{total_won}** 枚\n収支: **{total_won - total_price}** 枚"
        result_embed.add_field(name="💰 収支報告", value=summary, inline=False)
        result_embed.set_footer(text=f"当選数: {hit_count}/{count}")

        # DMへの送信
        try:
            await interaction.user.send(content=f"🎰 【{gacha_name}】 のガチャ結果です！", embed=result_embed)
        except discord.Forbidden:
            await interaction.followup.send("⚠️ DMが閉じているため、結果をDMに送れませんでした。以下に結果を表示します。", embed=result_embed, ephemeral=True)
        else:
            await interaction.followup.send("✅ 結果をDMに送信しました！", embed=rank_embed, ephemeral=True)

        # 7. ログ送信
        result_channel_id = 1499753452778029136
        result_chan = self.bot.get_channel(result_channel_id)
        if result_chan:
            log_embed = discord.Embed(title="🎰 ガチャ実行ログ", color=0x3498DB)
            log_embed.add_field(name="ユーザー", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="ガチャ名", value=gacha_name, inline=True)
            log_embed.add_field(name="結果", value=f"{count}連中 {hit_count}回当選", inline=True)
            log_embed.add_field(name="収支", value=f"{total_won - total_price} 枚", inline=True)
            await result_chan.send(embed=log_embed)

    @discord.ui.button(label="1連", style=discord.ButtonStyle.danger, emoji="🎰")
    async def roll_1(self, interaction: discord.Interaction, button: Button):
        await self.execute_rolls(interaction, 1)

    @discord.ui.button(label="10連", style=discord.ButtonStyle.primary, emoji="🔥")
    async def roll_10(self, interaction: discord.Interaction, button: Button):
        await self.execute_rolls(interaction, 10)

    @discord.ui.button(label="50連", style=discord.ButtonStyle.success, emoji="💎")
    async def roll_50(self, interaction: discord.Interaction, button: Button):
        await self.execute_rolls(interaction, 50)

# --- コインガチャCog ---
class CoinGacha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coin_gacha_add", description="【管理者】自動付与コインガチャを設置")
    async def coin_gacha_add(
        self, interaction: discord.Interaction, 名前: str, 価格: int, 当選コイン: int, カテゴリ: str, 表示確率: int = 50, 内部確率: float = 50.0, 画像: discord.Attachment = None
    ):
        await interaction.response.defer(ephemeral=True)
        img_url = 画像.url if 画像 else None
        
        data = {
            "name": 名前, 
            "price": 価格, 
            "win_coins": 当選コイン, 
            "command_name": カテゴリ.lower(), 
            "description": str(表示確率), 
            "max_slots": 内部確率,
            "image_url": img_url, 
            "active": True
        }
        
        self.bot.supabase.table("instant_oripa_items").insert(data).execute()
        await interaction.followup.send(f"✅ コインガチャ「{名前}」を設置しました。", ephemeral=True)

    @app_commands.command(name="coin_gacha", description="販売中のコインガチャを表示")
    async def coin_gacha(self, interaction: discord.Interaction, カテゴリ: str = None):
        await interaction.response.defer()
        query = self.bot.supabase.table("instant_oripa_items").select("*").eq("active", True).not_.is_("win_coins", "null")
        if カテゴリ: query = query.eq("command_name", カテゴリ.lower())
        res = query.execute()
        
        if not res.data: return await interaction.followup.send("販売中のコインガチャはありません。")
        
        for item in res.data:
            view = CoinGachaView(self.bot, item)
            embed = discord.Embed(title=f"💰 {item['name']}", color=0xF1C40F)
            embed.add_field(name="💳 価格", value=f"{item['price']} 枚", inline=True)
            embed.add_field(name="🎁 当選時", value=f"{item['win_coins']} 枚", inline=True)
            embed.add_field(name="📈 確率", value=f"{item['description']}%", inline=True)
            if item.get('image_url'): embed.set_image(url=item['image_url'])
            await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(CoinGacha(bot))