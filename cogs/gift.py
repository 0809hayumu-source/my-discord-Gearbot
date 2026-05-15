import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime

# --- 設定 ---
LOG_CHANNEL_ID = 1503306259200344144 

class GiftView(ui.View):
    def __init__(self, bot, amount: int, event_title: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.amount = amount
        self.event_title = event_title

    @ui.button(label="コインを受け取る", style=discord.ButtonStyle.success, emoji="💰", custom_id="gift_claim_btn")
    async def claim_gift(self, i: discord.Interaction, b: ui.Button):
        user_id = str(i.user.id)
        
        try:
            # 1. 重複チェック（保存されているタイトル文字列と比較）
            res = self.bot.supabase.table("user_coins").select("has_claimed_50").eq("user_id", user_id).execute()
            claimed_val = res.data[0].get('has_claimed_50') if (res.data and len(res.data) > 0) else None
            
            if claimed_val == self.event_title:
                return await i.response.send_message(f"❌ 「{self.event_title}」はすでに受け取り済みです。", ephemeral=True)

            # 2. フラグ更新（タイトルを保存） & コイン付与
            self.bot.supabase.table("user_coins").update({"has_claimed_50": self.event_title}).eq("user_id", user_id).execute()
            self.bot.supabase.rpc('update_user_stats', {'u_id': user_id, 'coin_change': self.amount}).execute()

            await i.response.send_message(f"✅ **{self.amount}枚** を受け取りました！", ephemeral=True)
            await self.send_gift_log(i.user, self.amount, self.event_title)
            
        except Exception as e:
            await i.response.send_message("⚠️ エラーが発生しました。管理者に連絡してください。", ephemeral=True)
            print(f"Gift Error: {e}")

    async def send_gift_log(self, user, amount, title):
        chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if not chan: return
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        log_emb = discord.Embed(title="📝 プレゼント配布記録", color=0xffd700)
        log_emb.description = (
            f"**ユーザー**　**結果**　**内容**\n"
            f"{user.mention}　済み　+{amount}枚\n\n"
            f"種別: {title} ・ 今日 {now.strftime('%H:%M')}"
        )
        await chan.send(embed=log_emb)

class GiftPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gift_panel", description="配布パネルを表示し、全員にメンションします")
    @app_commands.describe(title="パネルのタイトル", amount="付与するコインの枚数")
    @app_commands.checks.has_permissions(administrator=True)
    async def gift_panel(self, i: discord.Interaction, title: str, amount: int):
        emb = discord.Embed(
            title=f"🎊 {title}",
            description=(
                f"いつもありがとうございます！\n"
                f"全員に **{amount}枚** のコインをプレゼントします！\n\n"
                "下のボタンを押して受け取ってください。"
            ),
            color=0xffd700
        )
        emb.set_footer(text="※イベントごとに1回受け取り可能です")
        
        # 1. パネルを送信（ここで @everyone メンションを追加）
        await i.channel.send(content="@everyone", embed=emb, view=GiftView(self.bot, amount, title))
        
        # 2. 管理者への完了通知（自分だけに表示される）
        await i.response.send_message(f"✅ タイトル「{title}」で配布パネルを設置し、全員に通知しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(GiftPanel(bot))