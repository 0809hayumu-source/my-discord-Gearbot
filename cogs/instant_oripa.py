import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random
import asyncio
from utils import process_rank_system

# --- ガチャ実行View ---
class InstantOripaView(View):
    def __init__(self, bot, item):
        super().__init__(timeout=None)
        self.bot, self.item = bot, item

    async def execute_rolls(self, interaction: discord.Interaction, count: int):
        user_id = str(interaction.user.id)
        price_per_roll = self.item['price']
        total_price = price_per_roll * count
        
        # 1. 所持コインのチェック（支払い可能か確認）
        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", user_id).execute()
        current_coins = res.data[0].get("coin_count", 0) if res.data else 0
        
        if current_coins < total_price:
            return await interaction.response.send_message(f"❌ コイン不足 (必要: {total_price}枚 / 所持: {current_coins}枚)", ephemeral=True)

        # 2. 処理開始
        await interaction.response.defer(ephemeral=True)
        
        # 3. 【重要】これ一行で「コイン減算」「週間加算」「月間加算」「ランク判定」を全部実行
        # 以前の長い update 処理はすべてこの中に入っています
        rank_embed = await process_rank_system(self.bot, interaction.user.id, total_price)
        
        # 4. 抽選処理 (ここは変更なし)
        actual_win_rate = float(self.item.get('max_slots', 50))
        # ... (以下、抽選ロジックと結果表示) ...

        # 5. 最後に結果を表示する部分でランクゲージも送る
        # 既存のメッセージ送信などの後にこれを追加してください
        await interaction.followup.send(embed=rank_embed, ephemeral=True)
        # --- 以下の抽選処理へ続く ---
        # 支払い
        new_coins = current_coins - total_price
        self.bot.supabase.table("user_coins").upsert({"user_id": user_id, "coin_count": new_coins}).execute()

        # --- 抽選処理 ---
        actual_win_rate = float(self.item.get('max_slots', 50))
        gacha_name = self.item.get('name', "不明なガチャ")
        
        results_list = []
        hit_count = 0

        for i in range(1, count + 1):
            is_hit = random.uniform(0, 100) < actual_win_rate
            if is_hit:
                results_list.append(f"{i}回目: 🎊 当選")
                hit_count += 1
            else:
                results_list.append(f"{i}回目: 💀 ハズレ")

        # 演出
        await interaction.followup.send(f"🎰 「{gacha_name}」 {count}連ガチャを回しています...", ephemeral=True)
        await asyncio.sleep(1.2)

        # 結果Embed（カテゴリー表示を削除）
        result_embed = discord.Embed(
            title=f"🎰 {gacha_name} 結果 ({count}連)",
            description="\n".join(results_list),
            color=0xFFD700 if hit_count > 0 else 0x95A5A6
        )
        
        result_embed.set_footer(text=f"引いた人: {interaction.user.display_name} | 当選数: {hit_count}/{count}")

        # 結果送信（ログのメッセージからもカテゴリーを削除）
        result_channel_id = 1499753452778029136
        result_chan = self.bot.get_channel(result_channel_id)
        if result_chan:
            # ログ本文からも【カテゴリ】の表記をカット
            await result_chan.send(content=f"🎰 {interaction.user.mention} が 「{gacha_name}」 を回しました！", embed=result_embed)
            await interaction.edit_original_response(content=f"✅ 完了！ <#{result_channel_id}> を確認してください。")

    @discord.ui.button(label="1連", style=discord.ButtonStyle.danger, emoji="🎰")
    async def roll_1(self, interaction: discord.Interaction, button: Button):
        await self.execute_rolls(interaction, 1)

    @discord.ui.button(label="10連", style=discord.ButtonStyle.primary, emoji="🔥")
    async def roll_10(self, interaction: discord.Interaction, button: Button):
        await self.execute_rolls(interaction, 10)

    @discord.ui.button(label="50連", style=discord.ButtonStyle.success, emoji="💎")
    async def roll_50(self, interaction: discord.Interaction, button: Button):
        await self.execute_rolls(interaction, 50)

# --- ガチャCog ---
class InstantOripa(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="instant_oripa_add", description="【管理者】ガチャを設置")
    async def instant_oripa_add(
        self, interaction: discord.Interaction, 名前: str, 価格: int, カテゴリ: str, 表示確率: int = 50, 内部確率: float = 50.0, 画像: discord.Attachment = None
    ):
        await interaction.response.defer(ephemeral=True)
        img_url = 画像.url if 画像 else None
        data = {"name": 名前, "price": 価格, "prizes": "当選", "command_name": カテゴリ.lower(), "description": str(表示確率), "max_slots": int(round(内部確率)), "image_url": img_url, "active": True}
        self.bot.supabase.table("instant_oripa_items").insert(data).execute()
        await interaction.followup.send(f"✅ 「{名前}」を設置しました。\n**カテゴリ: {カテゴリ.lower()}**", ephemeral=True)

    @app_commands.command(name="instant_oripa", description="ガチャ一覧を表示")
    async def instant_oripa(self, interaction: discord.Interaction, カテゴリ: str = None):
        await interaction.response.defer()
        query = self.bot.supabase.table("instant_oripa_items").select("*").eq("active", True)
        if カテゴリ: query = query.eq("command_name", カテゴリ.lower())
        res = query.execute()
        if not res.data: return await interaction.followup.send("販売中のガチャはありません。")
        
        for item in res.data:
            # 設置時（一覧表示）には区別のためにカテゴリーを表示しておく
            view = InstantOripaView(self.bot, item)
            embed = discord.Embed(title=f"🎰 {item['name']}", color=0xF1C40F)
            embed.add_field(name="💰 価格", value=f"{item['price']} 枚/回", inline=True)
            embed.add_field(name="📈 確率", value=f"{item['description']}%", inline=True)
            embed.set_footer(text=f"カテゴリー: {item['command_name']}")
            if item.get('image_url'): embed.set_image(url=item['image_url'])
            await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(InstantOripa(bot))