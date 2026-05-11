import discord
from discord import app_commands, ui
from discord.ext import commands

# --- 設定 ---
LOG_CHANNEL_ID = 1503306259200344144  # 指定されたログチャンネルID
GIFT_AMOUNT = 100  # 配布する枚数

class GiftPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gift_panel", description="50人記念配布パネルを表示（管理者用）")
    @app_commands.checks.has_permissions(administrator=True)
    async def gift_panel(self, i: discord.Interaction):
        emb = discord.Embed(
            title="🎊 サーバー50人突破記念！",
            description=(
                f"いつもありがとうございます！\n"
                f"日頃の感謝を込めて、全員に **{GIFT_AMOUNT}枚** のコインをプレゼントします！\n\n"
                "下のボタンを押して受け取ってください。"
            ),
            color=0xffd700
        )
        await i.response.send_message(embed=emb, view=GiftView(self.bot))

class GiftView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # 半永久的に有効
        self.bot = bot

    @ui.button(label="コインを受け取る", style=discord.ButtonStyle.success, emoji="💰", custom_id="gift_button")
    async def claim_gift(self, i: discord.Interaction, b: ui.Button):
        user_id = str(i.user.id)
        
        try:
            # 1. 二重受け取り防止チェック
            res = self.bot.supabase.table("user_coins").select("has_claimed_50").eq("user_id", user_id).execute()
            
            if res.data and res.data[0].get('has_claimed_50'):
                return await i.response.send_message("❌ すでに受け取り済みです。", ephemeral=True)

            # 2. コイン追加 & 受け取り済みフラグを立てる
            # ※DBに 'has_claimed_50' カラムが必要です
            self.bot.supabase.table("user_coins").update({"has_claimed_50": True}).eq("user_id", user_id).execute()
            self.bot.supabase.rpc('update_user_stats', {'u_id': user_id, 'coin_change': GIFT_AMOUNT}).execute()

            # 3. ユーザーへの完了通知
            await i.response.send_message(f"✅ **{GIFT_AMOUNT}枚** を受け取りました！おめでとうございます！", ephemeral=True)
            
            # 4. ログ送信
            await self.send_gift_log(i.user)
            
        except Exception as e:
            await i.response.send_message("⚠️ エラーが発生したか、DBの準備ができていません。管理者に連絡してください。", ephemeral=True)
            print(f"Gift Error: {e}")

    async def send_gift_log(self, user):
        chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if not chan: return

        # 指定された「ユーザー、結果、内容」の形式に合わせたログ
        log_emb = discord.Embed(title="📝 プレゼント配布記録", color=0xffd700)
        log_emb.description = (
            f"**ユーザー**　**結果**　**内容**\n"
            f"{user.mention}　済み　+{GIFT_AMOUNT}枚\n\n"
            f"種別: 50人記念 ・ 今日 {discord.utils.utcnow().strftime('%H:%M')}"
        )
        await chan.send(embed=log_emb)

async def setup(bot):
    await bot.add_cog(GiftPanel(bot))