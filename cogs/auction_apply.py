import discord
from discord import app_commands, ui
from discord.ext import commands
# utils.py から process_rank_system をインポート
try:
    from utils import process_rank_system
except ImportError:
    # utilsがない場合のエラー回避（テスト用）
    async def process_rank_system(*args, **kwargs): return discord.Embed(description="Rank System Error")

# ==========================================
# 1. 管理者が押す「確認完了」ボタンView
# ==========================================
class AdminConfirmView(ui.View):
    # applicant_id などが None でも起動できるようにし、永続化に対応
    def __init__(self, bot, applicant_id=None, applicant_name=None, amount=100):
        super().__init__(timeout=None)
        self.bot = bot
        self.applicant_id = applicant_id
        self.applicant_name = applicant_name
        self.amount = amount

    @ui.button(label="PayPay受け取り確認完了", style=discord.ButtonStyle.success, emoji="✅", custom_id="admin_pay_confirm_btn")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        # 処理に時間がかかるため、応答を保留
        await interaction.response.defer(ephemeral=True)
        
        # 永続化時にデータが消えていた場合のフェイルセーフ（Embedから取得を試みる）
        if self.applicant_id is None:
            try:
                # EmbedのフィールドからユーザーIDを特定するなどの処理
                # ここではボタン生成時に渡された値を優先します
                return await interaction.followup.send("❌ 再起動後のデータ復元に失敗しました。手動で対応してください。", ephemeral=True)
            except: pass

        user_id_str = str(self.applicant_id)
        
        # 1. DBから進捗を加算
        try:
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
            applicant = await self.bot.fetch_user(self.applicant_id)
            if applicant:
                dm_embed = discord.Embed(
                    title="✅ オークション出品手数料の確認完了",
                    description=f"PayPay {self.amount}円の受け取りを確認しました！\nオークションの準備を開始します。\n\n**ランク進捗に反映されました！**",
                    color=discord.Color.green()
                )
                try:
                    await applicant.send(embed=dm_embed)
                    await applicant.send(embed=rank_embed)
                except discord.Forbidden:
                    print(f"{self.applicant_name} へのDM送信に失敗（閉じられています）")

            # 4. 管理画面の表示更新
            embed = interaction.message.embeds[0]
            embed.title = "✅ 【確認済み】支払い確認完了"
            embed.description = f"**{self.applicant_name}** 様の支払いを確認し、本人に通知を送りました。"
            embed.color = discord.Color.green()
            
            await interaction.message.edit(content=None, embed=embed, view=None)
            await interaction.followup.send(f"✅ {self.applicant_name} さんへランク反映のDMを送りました。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ エラーが発生しました: {e}", ephemeral=True)

# ==========================================
# 2. 申請モーダル
# ==========================================
class AuctionApplyModal(ui.Modal, title="オークション出品申請"):
    item_name = ui.TextInput(label="出品したい商品名", placeholder="例：ノマドラ〇〇変異")
    pay_url = ui.TextInput(label="PayPay(手数料100円)", placeholder="例：https://paypayURL")
    description = ui.TextInput(label="詳細", style=discord.TextStyle.paragraph, required=False, placeholder="例：初期値段は500円から...")

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        FEE_AMOUNT = 100 
        ADMIN_CHANNEL_ID = 1502509796690104370 
        
        admin_channel = self.bot.get_channel(ADMIN_CHANNEL_ID)
        if not admin_channel:
            return await interaction.followup.send("⚠️ 管理チャンネルが見つかりません。", ephemeral=True)

        admin_embed = discord.Embed(title="🎟️ オークション申請 (未確認)", color=0xffd700)
        admin_embed.add_field(name="申請者", value=interaction.user.mention, inline=True)
        admin_embed.add_field(name="商品名", value=self.item_name.value, inline=True)
        admin_embed.add_field(name="PayPay", value=self.pay_url.value, inline=True)
        admin_embed.set_footer(text="確認完了ボタンを押すとランク反映されます")

        view = AdminConfirmView(self.bot, interaction.user.id, interaction.user.display_name, FEE_AMOUNT)
        await admin_channel.send(
            content=f"🚨 **{interaction.user.display_name}様から申請。100円の確認をお願いします！**",
            embed=admin_embed,
            view=view
        )
        await interaction.followup.send("✅ 申請を受け付けました！管理者が確認次第、DMでお知らせします！", ephemeral=True)

# ==========================================
# 3. パネルView & Cog
# ==========================================
class AuctionApplyView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="出品を申請する (100PayPay円)", style=discord.ButtonStyle.primary, emoji="🎟️", custom_id="auction_apply_btn")
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AuctionApplyModal(self.bot))

class AuctionApplyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_auction_ticket", description="オークション申請ボタンを設置します")
    async def setup_auction_ticket(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)

        embed = discord.Embed(
            title="🔨 オークション出品受付",
            description="下のボタンから申請してください。\n\n100円分のランク反映が適用されます。",
            color=discord.Color.blue()
        )
        await interaction.channel.send(embed=embed, view=AuctionApplyView(self.bot))
        await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AuctionApplyCog(bot))