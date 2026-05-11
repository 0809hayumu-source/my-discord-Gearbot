import discord
from discord import app_commands, ui
from discord.ext import commands
from utils import process_rank_system

# ==========================================
# 1. 管理者が押す「確認完了」ボタンView
# ==========================================
class AdminConfirmView(ui.View):
    def __init__(self, bot, applicant_id, applicant_name, amount):
        super().__init__(timeout=None)
        self.bot = bot
        self.applicant_id = applicant_id
        self.applicant_name = applicant_name
        self.amount = amount

    @ui.button(label="PayPay受け取り確認完了", style=discord.ButtonStyle.success, emoji="✅", custom_id="admin_pay_confirm_btn")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        # --- 💎 修正：処理に時間がかかるため、まず応答を保留(defer)にする ---
        await interaction.response.defer(ephemeral=True)
        
        user_id_str = str(self.applicant_id)
        
        # 1. DBから進捗を加算
        res = self.bot.supabase.table("user_coins").select("*").eq("user_id", user_id_str).execute()
        if res.data:
            user_data = res.data[0]
            new_monthly = user_data.get("monthly_spent", 0) + self.amount
            new_weekly = user_data.get("weekly_spent", 0) + self.amount
            self.bot.supabase.table("user_coins").update({
                "monthly_spent": new_monthly, "weekly_spent": new_weekly
            }).eq("user_id", user_id_str).execute()

        # 2. ランク判定とランクEmbed作成
        rank_embed = await process_rank_system(self.bot, self.applicant_id, 0)

        # 3. 申請者本人へのDM通知
        try:
            applicant = await self.bot.fetch_user(self.applicant_id)
            if applicant:
                dm_embed = discord.Embed(
                    title="✅ オークション出品手数料の確認完了",
                    description=f"PayPay 100円の受け取りを確認しました！\nオークションの準備を開始します。\n\n**ランク進捗に反映されました！**",
                    color=discord.Color.green()
                )
                await applicant.send(embed=dm_embed)
                await applicant.send(embed=rank_embed) # ランクバーをDMに添付
        except Exception as e:
            print(f"DM送信失敗: {e}")

        # 4. 管理画面の表示更新
        embed = interaction.message.embeds[0]
        embed.title = "✅ 【確認済み】支払い確認完了"
        embed.description = f"**{self.applicant_name}** 様の支払いを確認し、本人に通知を送りました。"
        embed.color = discord.Color.green()
        
        # 編集と完了報告
        await interaction.message.edit(content=None, embed=embed, view=None)
        await interaction.followup.send(f"✅ {self.applicant_name} さんへランク反映のDMを送りました。", ephemeral=True)

# ==========================================
# 2. Cogクラス
# ==========================================
class AuctionApplyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_auction_ticket", description="オークション申請ボタンを設置します")
    async def setup_auction_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔨 オークション出品受付",
            description=(
                "下のボタンから申請してください。\n\n"
                "**【流れ】**\n"
                "1. ボタンを押して内容を入力\n"
                "2. PayPay 100円を送金\n"
                "3. **管理者が確認後、DMで通知が届きランクUP！※100円分ランクが上がります。**"
            ),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=AuctionApplyView(self.bot))

# ==========================================
# 3. モーダルクラス
# ==========================================
class AuctionApplyModal(ui.Modal, title="オークション出品申請"):
    item_name = ui.TextInput(label="出品したい商品名", placeholder="例：ノマドラ〇〇変異")
    start_price = ui.TextInput(label="PayPay(手数料100円)", placeholder="例：https://paypayURL")
    description = ui.TextInput(label="詳細", style=discord.TextStyle.paragraph, required=False ,placeholder="例：初期値段は500円から締め切りは３時間後でお願いします。")

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        FEE_AMOUNT = 100 
        
        # 通知先チャンネル（テキストチャンネル）
        ADMIN_CHANNEL_ID = 1502509796690104370 
        admin_channel = self.bot.get_channel(ADMIN_CHANNEL_ID)

        admin_embed = discord.Embed(title="🎟️ オークション申請 (未確認)", color=0xffd700)
        admin_embed.add_field(name="申請者", value=interaction.user.mention, inline=True)
        admin_embed.add_field(name="商品名", value=self.item_name.value, inline=True)
        admin_embed.add_field(name="金額", value=f"{self.start_price.value}円", inline=True)
        admin_embed.set_footer(text="確認完了ボタンを押すと本人にDMが飛び、ランク反映されます")

        if admin_channel:
            view = AdminConfirmView(self.bot, interaction.user.id, interaction.user.display_name, FEE_AMOUNT)
            await admin_channel.send(
                content=f"🚨 **{interaction.user.display_name}様から申請。100円の確認をお願いします！**",
                embed=admin_embed,
                view=view
            )
            await interaction.followup.send("✅ 申請を受け付けました！\n管理者が確認次第、あなたのランクが更新され、DMでお知らせします！", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ エラー：管理チャンネルが見つかりませんでした。", ephemeral=True)

# ==========================================
# 4. Viewクラス
# ==========================================
class AuctionApplyView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="出品を申請する (100PayPay円)", style=discord.ButtonStyle.primary, emoji="🎟️", custom_id="auction_apply_btn")
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AuctionApplyModal(self.bot))

async def setup(bot):
    await bot.add_cog(AuctionApplyCog(bot))