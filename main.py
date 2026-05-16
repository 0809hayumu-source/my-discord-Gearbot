import discord
from discord.ext import commands
import os
from supabase import create_client, Client
import datetime

# --- 設定項目 ---
TOKEN = os.getenv("TOKEN") or "MTM1ODAyNDA2MjkxMTM4NTczMg.GzoW9w.8p4tjwMP_tik-qmCICmczFyoMnhgKbP2ssGehI"
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

        # オークション申請 (追加分)
        try:
            from cogs.auction_apply import AuctionApplyView, AdminConfirmView
            self.add_view(AuctionApplyView(self))
            self.add_view(AdminConfirmView(self))
            print("✅ オークションボタンを復旧")
        except Exception as e: print(f"⚠️ オークションViewの登録失敗: {e}")

        # --- 2. Cogの自動読み込み ---
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    # 読み込み済みの拡張子と重複しないようにチェック（任意）
                    ext = f'cogs.{filename[:-3]}'
                    if ext not in self.extensions:
                        await self.load_extension(ext)
                        print(f"📦 Cog読み込み完了: {filename}")
                except Exception as e:
                    print(f"❌ {filename} の読み込みに失敗しました: {e}")
                    
        async def setup_hook(self):
        # --- (他の登録は省略) ---

        # 配布パネルの永続化登録
                try:
                    from cogs.gift import GiftView
            # 登録時に amount を渡す必要があります（再起動後の判定用）
                    self.add_view(GiftView(self, amount=0)) 
                    print("✅ 配布ボタンを復旧")
                except Exception as e: 
                    print(f"⚠️ 配布ボタンの登録失敗: {e}")

        # --- (Cogのロード) ---
        
        # スラッシュコマンドを確実に同期させる
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        # --- 3. スラッシュコマンドの同期 ---
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        await self.tree.sync() # グローバル同期
        
        print(f"🚀 {self.user} 起動完了！すべての機能が正常にロードされました。")

bot = MyBot()
bot.run(TOKEN)