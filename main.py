import discord
from discord.ext import commands
import os
from supabase import create_client, Client

# --- 設定項目 ---
TOKEN = "MTM1ODAyNDA2MjkxMTM4NTczMg.G2SxMz.8Z5sCUXECq_JuqXjrR4gG1BV5D4Rg1Zr2nUSIg"
SUPABASE_URL = "https://vlkydiqtnojdpeictmfy.supabase.co"
SUPABASE_KEY = "sb_publishable_flcUiiaSmbpVYgaCMuenQQ_wkUJ7EG2" 
GUILD_ID = 1492877145964286062

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def load_data(self, user_id):
        try:
            res = self.supabase.table("user_coins").select("coin_count").eq("user_id", str(user_id)).execute()
            return res.data[0].get("coin_count", 0) if res.data else 0
        except: return 0

    def add_data(self, user_id, coins=0):
        curr_c = self.load_data(user_id)
        self.supabase.table("user_coins").upsert({
            "user_id": str(user_id), 
            "coin_count": int(curr_c + coins)
        }).execute()

    async def setup_hook(self):
        # --- ここから追加：ボタンの永続化設定 ---
        # 認証システムのViewをインポートして登録
        # (cogs/verify.py にクラスがある前提です)
        try:
            from cogs.verify import VerifyView, AdminApprovalView
            # ユーザーIDを一時的にNoneで登録しておくことで、
            # 再起動後のボタン押下時に interaction から情報を拾えるようにします
            self.add_view(VerifyView())
            self.add_view(AdminApprovalView(user=None)) 
            print("✅ 認証ボタンの待機状態を復旧しました")
        except Exception as e:
            print(f"⚠️ Viewの登録に失敗しました: {e}")
        # --- ここまで追加 ---

        # cogsフォルダ内のファイルを自動読み込み
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print(f"✅ {self.user} 起動（機能を分割して読み込み完了）")

bot = MyBot()
bot.run(TOKEN)