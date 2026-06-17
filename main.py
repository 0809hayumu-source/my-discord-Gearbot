import discord
from discord.ext import commands
from discord.ui import View
import os 
from supabase import create_client, Client
import datetime

# --- 設定項目 ---
TOKEN = os.getenv("MTM1ODAyNDA2MjkxMTM4NTczMg.GioyNC.7AE_5QjknnCsJcAnLKMSSm44tuaesp2gi2DiwI")
if not TOKEN:
    raise ValueError("エラー: TOKENが環境変数に設定されていません！")
SUPABASE_URL = "https://vlkydiqtnojdpeictmfy.supabase.co"
SUPABASE_KEY = "sb_publishable_flcUiiaSmbpVYgaCMuenQQ_wkUJ7EG2" 
GUILD_ID = 1492877145964286062

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # データベース操作（既存）
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
        """ボット起動時に一度だけ実行される処理（すべてのViewとCogをここで登録）"""
        
        # --- 1. 永続化Viewの一括登録エリア ---
        
        # 認証システム
        try:
            from cogs.verify import VerifyView, AdminApprovalView
            self.add_view(VerifyView())
            self.add_view(AdminApprovalView(user=None))
            print("✅ 認証ボタンを復旧")
        except Exception as e: print(f"⚠️ 認証Viewの登録失敗: {e}")

        # コインショップ
        try:
            from cogs.shop import ShopView, AdminCoinVerifyView
            self.add_view(ShopView(self))
            self.add_view(AdminCoinVerifyView(self))
            print("✅ ショップボタンを復旧")
        except Exception as e: print(f"⚠️ ショップViewの登録失敗: {e}")

        # 自販機
        try:
            from cogs.vending import VendingView, AdminVendingVerifyView
            self.add_view(VendingView(self))
            self.add_view(AdminVendingVerifyView()) 
            print("✅ 自販機ボタンを復旧")
        except Exception as e: print(f"⚠️ 自販機Viewの登録失敗: {e}")

        # ガチャ
        try:
            from cogs.gacha import GachaMenuView, AdminGachaVerifyView, GachaExecuteView, CoinGachaConfirmView
            self.add_view(GachaMenuView(self))
            self.add_view(AdminGachaVerifyView())
            self.add_view(GachaExecuteView())
            self.add_view(CoinGachaConfirmView())
            print("✅ ガチャボタンを復旧")
        except Exception as e: print(f"⚠️ ガチャViewの登録失敗: {e}")

        # オリパ
        try:
            from cogs.oripa import ReservedOripaView
            res = self.supabase.table("oripa_items").select("*").eq("active", True).execute()
            for item in res.data:
                res_count = self.supabase.table("oripa_reservations").select("id", count="exact").eq("oripa_id", item['id']).execute()
                count = res_count.count if res_count.count is not None else 0
                self.add_view(ReservedOripaView(self, item, count))
            print(f"✅ オリパViewを {len(res.data)} 件復旧")
        except Exception as e: print(f"⚠️ オリパViewの復旧失敗: {e}")

        # ブラックジャック
        try:
            from cogs.blackjack import BJMainView
            self.add_view(BJMainView(self))
            print("✅ BJパネルのボタンを復旧")
        except Exception as e: print(f"⚠️ BJViewの登録失敗: {e}")

        # バカラ
        try:
            from cogs.baccarat import BaccaratMainView
            self.add_view(BaccaratMainView(self))
            print("✅ バカラパネルのボタンを復旧")
        except Exception as e: print(f"⚠️ バカラViewの登録失敗: {e}")
        
        # マルチブラックジャックパネルの永続化
        try:
            from cogs.blackjack_multi import BJPanelView
            self.add_view(BJPanelView(self))
            print("✅ マルチBJパネルのボタンを復旧")
        except Exception as e: print(f"⚠️ マルチBJViewの登録失敗: {e}")

        # オークション申請
        try:
            from cogs.auction_apply import AuctionApplyView, AdminConfirmView
            self.add_view(AuctionApplyView(self))
            self.add_view(AdminConfirmView(self))
            print("✅ オークションボタンを復旧")
        except Exception as e: print(f"⚠️ オークションViewの登録失敗: {e}")

        # 配布パネルの永続化登録
        try:
            from cogs.gift import GiftView
            self.add_view(GiftView(self, amount=0)) 
            print("✅ 配布ボタンを復旧")
        except Exception as e: print(f"⚠️ 配布ボタンの登録失敗: {e}")

        # チケットシステムパネルと閉じるボタンの永続化
        try:
            from cogs.ticket_system import PayTicketPanelView, TicketCloseView
            self.add_view(PayTicketPanelView(self))
            self.add_view(TicketCloseView(self))
            print("✅ チケットシステム（発行・クローズ）を復旧")
        except Exception as e: print(f"⚠️ チケットViewの登録失敗: {e}")

        # ロブロックスチケットシステムの永続化
        try:
            from cogs.roblox_ticket import RobloxTicketPanelView, RobloxTicketCloseView
            self.add_view(RobloxTicketPanelView(self))
            self.add_view(RobloxTicketCloseView(self))
            print("✅ ロブロックスチケットシステムを復旧")
        except Exception as e: print(f"⚠️ ロブロチケットViewの登録失敗: {e}")

        # ポーカー常駐パネルの永続化
        try:
            from cogs.poker_system import PokerPanelLaunchView
            self.add_view(PokerPanelLaunchView(self))
            print("✅ ポーカー常駐パネルを復旧")
        except Exception as e: print(f"⚠️ ポーカーパネルViewの登録失敗: {e}")

        # 🧪 テストユーザー募集パネルの永続化
        try:
            from cogs.test_user_recruitment import TestUserButtonView
            self.add_view(TestUserButtonView())
            print("✅ テストユーザーボタンを復旧")
        except Exception as e: print(f"⚠️ テストユーザーボタンViewの登録失敗: {e}")

        # 🤝 仲介チケットパネルの永続化 【✨ここを完全に最新版に修正✨】
        try:
            from cogs.mm_ticket import TicketLaunchView, TicketCombinedControlView
            self.add_view(TicketLaunchView())
            self.add_view(TicketCombinedControlView(show_invite=False)) # 2ボタン版
            self.add_view(TicketCombinedControlView(show_invite=True))  # 3ボタン版（追加し忘れ対応用）
            print("✅ 仲介チケットパネル一式（動的ボタン対応）を正常に復旧")
        except Exception as e: 
            print(f"⚠️ 仲介チケットViewの登録失敗: {e}")

        @commands.command()
        async def sync(self, ctx):
            await self.bot.tree.sync()
            await ctx.send("コマンドを同期しました！")


        # --- 2. Cogの自動読み込み ---
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    ext = f'cogs.{filename[:-3]}'
                    if ext not in self.extensions:
                        await self.load_extension(ext)
                        print(f"📦 Cog読み込み完了: {filename}")
                except Exception as e:
                    print(f"❌ {filename} の読み込みに失敗しました: {e}")

        # Cogの中、またはbot.runの直前などに必要な同期処理
        @commands.command()
        async def sync(self, ctx):
            await self.bot.tree.sync()
            await ctx.send("コマンドを同期しました！")


        # --- 3. スラッシュコマンドの同期 ---
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        await self.tree.sync() # グローバル同期

    async def on_ready(self):
        """Botが完全に起動したときに実行される処理"""
        print(f"🚀 {self.user} 起動完了！すべての機能と永続化ボタンが正常にロードされました。")

if __name__ == "__main__":
    bot = MyBot()
    
    # 最後に run を1回だけ呼び出す（ループは bot.run の中で制御する）
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ 致命的なエラー: {e}")