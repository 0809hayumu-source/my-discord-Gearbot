
import discord
from discord.ext import commands
import os 
from supabase import create_client, Client

# --- 設定項目 ---
# ⚠️ ここに新しいトークンを直接貼り付けてください
TOKEN = "MTM1ODAyNDA2MjkxMTM4NTczMg.GzoW9w.8p4tjwMP_tik-qmCICmczFyoMnhgKbP2ssGehI"
SUPABASE_URL = "https://vlkydiqtnojdpeictmfy.supabase.co"
SUPABASE_KEY = "sb_publishable_flcUiiaSmbpVYgaCMuenQQ_wkUJ7EG2" 
GUILD_ID = 1492877145964286062

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    async def setup_hook(self):
        # 1. まず全Cogを読み込む
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"📦 Cog読み込み完了: {filename}")
                except Exception as e:
                    print(f"❌ {filename} の読み込み失敗: {e}")

        # 2. Cog読み込み完了後にViewを登録する
        try:
            from cogs.mm_ticket import TicketLaunchView, TicketCombinedControlView
            self.add_view(TicketLaunchView())
            self.add_view(TicketCombinedControlView(show_invite=False))
            self.add_view(TicketCombinedControlView(show_invite=True))
            print("✅ 仲介チケットViewを復旧")
        except Exception as e:
            print(f"⚠️ View登録失敗: {e}")

        # 3. コマンド同期
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("✅ スラッシュコマンドの同期完了")

bot = MyBot()

@bot.command()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("同期しました！")

bot.run(TOKEN)