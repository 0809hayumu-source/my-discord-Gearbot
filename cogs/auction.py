import discord
from discord import app_commands, ui
from discord.ext import commands  # ← これを追加！
import asyncio
from datetime import datetime, timedelta
import random

# --- 入札用モーダル ---
class BidModal(ui.Modal, title="入札価格を入力"):
    bid_amount = ui.TextInput(label="入札金額 (PayPay円)", placeholder="現在の価格より高い数値を入力", min_length=1)

    def __init__(self, bot, embed, current_price):
        super().__init__()
        self.bot = bot
        self.embed = embed
        self.current_price = current_price

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.bid_amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ 半角数字で金額を入力してください。", ephemeral=True)

        if amount <= self.current_price:
            return await interaction.response.send_message(f"❌ 現在の価格（{self.current_price}円）より高い金額を入力してください。", ephemeral=True)

        # 表示の更新
        self.embed.set_field_at(0, name="現在の最高価格", value=f"💴 **{amount:,} PayPay円**", inline=True)
        self.embed.set_field_at(1, name="最高入札者", value=interaction.user.mention, inline=True)
        
        view = ui.View(timeout=None)
        view.add_item(BidButton(self.bot, amount))
        
        await interaction.message.edit(embed=self.embed, view=view)
        await interaction.response.send_message(f"✅ {amount:,}円で入札しました！", ephemeral=True)

# --- 入札ボタン ---
class BidButton(ui.Button):
    def __init__(self, bot, current_price):
        super().__init__(label=f"🔨 入札 (現在:{current_price:,}円)", style=discord.ButtonStyle.success)
        self.bot = bot
        self.current_price = current_price

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BidModal(self.bot, interaction.message.embeds[0], self.current_price))

# --- メインのオークションCog ---
class AuctionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="auction_start", description="【管理者専用】PayPayオークションを開始します")
    @app_commands.describe(
        item_name="商品名",
        start_price="開始価格(PayPay円)",
        duration_minutes="終了までの時間(分)",
        image="商品の写真"
    )
    async def auction_start(self, interaction: discord.Interaction, item_name: str, start_price: int, duration_minutes: int, image: discord.Attachment):
        # 1. 画像チェック
        if not image.content_type.startswith("image/"):
            return await interaction.response.send_message("❌ 画像ファイルをアップロードしてください。", ephemeral=True)

        await interaction.response.defer()

        # 2. 終了時刻の計算
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        end_time_str = end_time.strftime('%H:%M:%S')

        # 3. Embed作成
        embed = discord.Embed(
            title=f"📢 PayPayオークション: {item_name}",
            description=f"⏰ **終了予定: {end_time_str}** ({duration_minutes}分間)\n⚠️ 落札後はPayPayでの支払いとなります。",
            color=0xff0033 # PayPayカラーの赤
        )
        embed.add_field(name="現在の最高価格", value=f"💴 **{start_price:,} PayPay円**", inline=True)
        embed.add_field(name="最高入札者", value="なし", inline=True)
        embed.set_image(url=image.url)
        embed.set_footer(text=f"出品管理: {interaction.user.display_name}")

        view = ui.View(timeout=None)
        view.add_item(BidButton(self.bot, start_price))

        # 4. パネル送信
        msg = await interaction.followup.send(f"🔨 オークションを開始しました！", embed=embed, view=view)

        # 5. 時間切れまで待機して自動終了
        await asyncio.sleep(duration_minutes * 60)

        # 6. 終了処理
        # 最新のメッセージ状態を取得して落札者を特定
        try:
            final_msg = await interaction.channel.fetch_message(msg.id)
            final_embed = final_msg.embeds[0]
            winner = final_embed.fields[1].value
            final_price = final_embed.fields[0].value

            final_embed.title = f"🚨 【終了】{item_name}"
            final_embed.color = discord.Color.default()
            final_embed.description = f"✅ オークションは終了しました。\n落札者: {winner}\n最終価格: {final_price}"
            
            await final_msg.edit(embed=final_embed, view=None) # ボタンを消す
            await interaction.channel.send(f"🎊 オークション終了！\n{item_name} は {winner} さんが {final_price} で落札しました！DM等でPayPayのやり取りを行ってください。")
        except Exception as e:
            print(f"終了処理エラー: {e}")

async def setup(bot):
    await bot.add_cog(AuctionCog(bot))