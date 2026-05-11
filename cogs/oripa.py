import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import random
import asyncio
from utils import process_rank_system

# --- 予約ログ用チャンネルID ---
LOG_CHANNEL_ID = 1498696009797075176

# --- 予約用モーダル ---
class OripaReserveModal(Modal):
    def __init__(self, view, item):
        super().__init__(title=f"予約：{item['name']}")
        self.view, self.item = view, item
        self.amount = TextInput(
            label=f"購入口数 (一人最大 {item['user_limit']} 口)", 
            placeholder=f"1～{item['user_limit']}の数字を入力", 
            min_length=1, max_length=2, required=True
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            buy_count = int(self.amount.value)
        except:
            return await interaction.followup.send("❌ 数字を入力してください。", ephemeral=True)

        user_id = str(interaction.user.id)
        oripa_id = self.item['id']
        
        # --- 最新の予約状況をDBから取得 ---
        res_res = self.view.bot.supabase.table("oripa_reservations").select("user_id").eq("oripa_id", oripa_id).execute()
        db_reserved_ids = [r['user_id'] for r in res_res.data]
        
        already_reserved = db_reserved_ids.count(user_id)
        user_limit = self.item['user_limit']
        
        if already_reserved + buy_count > user_limit:
            return await interaction.followup.send(
                f"❌ 購入制限エラー：このオリパは1人最大 {user_limit} 口までです。\n"
                f"（現在 {already_reserved} 口予約済み）", 
                ephemeral=True
            )

        remaining = self.item['max_slots'] - len(db_reserved_ids)
        if buy_count > remaining or buy_count <= 0:
            return await interaction.followup.send(f"❌ 残り口数エラー（残り {remaining} 口）", ephemeral=True)
        
        # 1. 支払い可能かチェック（現在のコイン数のみ取得）
        res = self.view.bot.supabase.table("user_coins").select("coin_count").eq("user_id", user_id).execute()
        current_coins = res.data[0].get("coin_count", 0) if res.data else 0
        
        total_price = self.item['price'] * buy_count
        
        if current_coins < total_price:
            return await interaction.followup.send(f"❌ コイン不足 (必要: {total_price}枚 / 所持: {current_coins}枚)", ephemeral=True)
        
        # 2. 【重要】これ一行で「コイン減算」「週間加算」「月間加算」「ランク判定」を全部実行
        # 手動の長い update ブロックは削除してこれに差し替えます
        rank_embed = await process_rank_system(self.view.bot, interaction.user.id, total_price)

        # 3. 予約登録処理 (ここは元のロジックを維持)
        # self.view.bot.supabase.table("oripa_reservations").insert(...) 等が続く
        # --- DBに予約を保存 ---
        for _ in range(buy_count):
            self.view.bot.supabase.table("oripa_reservations").insert({"oripa_id": oripa_id, "user_id": user_id}).execute()
        
        # 📢 予約ログ送信
        log_chan = self.view.bot.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            await log_chan.send(f"📝 **予約ログ**: {interaction.user.mention} が 「{self.item['name']}」を **{buy_count}口** 予約しました。")

        # 最新の件数で表示更新
        new_total = len(db_reserved_ids) + buy_count
        self.view.reserve_btn.label = f"予約する ({new_total}/{self.item['max_slots']})"
        
        if new_total >= self.item['max_slots']:
            self.view.reserve_btn.disabled, self.view.reserve_btn.label = True, "完売・抽選中"
            await interaction.message.edit(view=self.view)
            await self.view.run_lottery(interaction, oripa_id)
        else:
            await interaction.message.edit(view=self.view)
            await interaction.followup.send(f"✅ {buy_count}口予約完了！（合計: {already_reserved + buy_count}口）", ephemeral=True)

# --- オリパ表示View ---
class ReservedOripaView(View):
    def __init__(self, bot, item, current_count):
        super().__init__(timeout=None)
        self.bot, self.item = bot, item
        # ボタンのラベルにDBから取得した現在の予約数を反映
        self.reserve_btn.label = f"予約する ({current_count}/{item['max_slots']})"
        if current_count >= item['max_slots']:
            self.reserve_btn.disabled, self.reserve_btn.label = True, "完売・抽選中"

    @discord.ui.button(label="予約する", style=discord.ButtonStyle.danger, emoji="🔥")
    async def reserve_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(OripaReserveModal(self, self.item))

    async def run_lottery(self, interaction, oripa_id):
        result_channel_id = 1497445916406448320
        chan = self.bot.get_channel(result_channel_id)
        if not chan: return

        await chan.send(f"📢 **{self.item['name']}** 完売！抽選を開始します...")
        await asyncio.sleep(3)

        # DBから確定した予約者リストを取得
        res = self.bot.supabase.table("oripa_reservations").select("user_id").eq("oripa_id", oripa_id).execute()
        ids = [r['user_id'] for r in res.data]
        random.shuffle(ids)
        
        prize_data = self.item.get('prizes', "")
        prizes_dict = {} 
        all_prizes = []
        if prize_data:
            for p in prize_data.split(','):
                if ':' in p:
                    p_name, count = p.split(':')
                    all_prizes.extend([p_name] * int(count))
        
        back_coin = self.item.get('back_coin_amount', 0)
        
        for i, user_id in enumerate(ids):
            prize_name = all_prizes[i] if i < len(all_prizes) else "参加賞"
            if prize_name not in prizes_dict: prizes_dict[prize_name] = []
            prizes_dict[prize_name].append(f"<@{user_id}>")
            
            if prize_name == "参加賞" and back_coin > 0:
                c_res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", user_id).execute()
                curr = c_res.data[0]['coin_count'] if c_res.data else 0
                self.bot.supabase.table("user_coins").upsert({"user_id": user_id, "coin_count": curr + back_coin}).execute()

        embed = discord.Embed(title=f"🎉 【{self.item['name']}】 抽選結果", color=0xFFD700)
        for p_name, users in prizes_dict.items():
            embed.add_field(name=f"🎉 当選：{p_name}", value="\n".join(users), inline=False)

        await chan.send(embed=embed)
        # オリパ終了処理
        self.bot.supabase.table("oripa_items").update({"active": False}).eq("id", oripa_id).execute()
        # 予約データもクリーンアップ（任意）
        # self.bot.supabase.table("oripa_reservations").delete().eq("oripa_id", oripa_id).execute()

        # --- oripa.py の該当箇所を以下に書き換え ---
        if prize_name == "参加賞" and back_coin > 0:
                c_res = self.bot.supabase.table("user_coins").select("coin_count, weekly_gain").eq("user_id", user_id).execute()
                curr = c_res.data[0]['coin_count'] if c_res.data else 0
                curr_weekly = c_res.data[0].get('weekly_gain', 0) if c_res.data else 0 # 週間分を取得
                
                # 所持金と今週の獲得分を両方更新
                self.bot.supabase.table("user_coins").upsert({
                    "user_id": user_id, 
                    "coin_count": curr + back_coin,
                    "weekly_gain": curr_weekly + back_coin # 今週分を加算
                }).execute()

# --- オリパCog ---
class Oripa(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="oripa_add", description="【管理者】詳細設定付きでオリパを登録")
    @app_commands.rename(name="オリパ名", subtitle="説明文", price="価格", category="カテゴリ名", max_slots="総口数", prizes="当たり内容", user_limit="購入制限", back_coin="最低保証", image="画像")
    @app_commands.checks.has_permissions(administrator=True)
    async def oripa_add(self, interaction: discord.Interaction, name: str, price: int, category: str, max_slots: int, prizes: str, subtitle: str = None, user_limit: int = 1, back_coin: int = 0, image: discord.Attachment = None):
        await interaction.response.defer(ephemeral=True)
        img_url = image.url if image else None
        data = {"name": name, "description": subtitle, "price": price, "command_name": category.lower(), "max_slots": max_slots, "prizes": prizes, "user_limit": user_limit, "back_coin_amount": back_coin, "image_url": img_url, "active": True}
        self.bot.supabase.table("oripa_items").insert(data).execute()
        
        await interaction.followup.send(
            f"@everyone ✅ 「{name}」を登録しました！\n"
            f"**カテゴリー名: {category.lower()}**", 
            ephemeral=True
        )

    @app_commands.command(name="oripa", description="販売中のオリパを表示")
    @app_commands.rename(category="カテゴリ名")
    async def oripa(self, interaction: discord.Interaction, category: str = "oripa"):
        await interaction.response.defer()
        res = self.bot.supabase.table("oripa_items").select("*").eq("command_name", category.lower()).eq("active", True).execute()
        if not res.data: return await interaction.followup.send(f"現在販売中のオリパはありません。")
        
        for item in res.data:
            # DBから現在の予約済み件数を取得
            res_count = self.bot.supabase.table("oripa_reservations").select("id", count="exact").eq("oripa_id", item['id']).execute()
            current_count = res_count.count if res_count.count is not None else 0
            
            view = ReservedOripaView(self.bot, item, current_count)
            embed = discord.Embed(title=f"🃏 {item['name']}", color=0xF1C40F)
            if item.get('description'): embed.description = item['description']
            embed.add_field(name="💰 価格", value=f"{item['price']} 枚", inline=True)
            embed.add_field(name="📦 総口数", value=f"{item['max_slots']} 口", inline=True)
            embed.add_field(name="👤 制限", value=f"最大 {item['user_limit']} 口", inline=True)
            embed.set_footer(text=f"カテゴリ: {item['command_name']}")
            
            if item.get('image_url'): embed.set_image(url=item['image_url'])
            await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Oripa(bot))