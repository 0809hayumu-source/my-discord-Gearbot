import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio
import datetime
from utils import process_rank_system

# --- 設定 ---
LOG_CHANNEL_ID = 1509036075010752734            # 🛑 ログチャンネルID
RESULT_HISTORY_CHANNEL_ID = 1509036329621786655  # 📅 履歴チャンネルID

class CrashPlayer:
    def __init__(self, user, bet_amount, auto_cashout_at=None):
        self.user = user
        self.bet_amount = bet_amount  # 0の場合は「test」プレイ
        self.auto_cashout_at = auto_cashout_at  # 自動利確倍率 (None または float)
        self.cashed_out = False
        self.payout_multiplier = 0.0
        self.profit = 0

# --- 💵 ベット用モーダル ---
class CrashBetModal(discord.ui.Modal, title="💸 クラッシュにベット"):
    bet_input = discord.ui.TextInput(
        label="ベットするコイン数を入力してください", 
        placeholder="例: 500 (テストプレイは test )", 
        min_length=1, max_length=10, required=True
    )
    auto_input = discord.ui.TextInput(
        label="自動利確（キャッシュアウト）倍率 【任意】", 
        placeholder="例: 2.5 (空欄なら手動のみ)", 
        min_length=0, max_length=6, required=False
    )

    def __init__(self, game_view):
        super().__init__()
        self.view = game_view

    async def on_submit(self, i: discord.Interaction):
        if self.view.game_phase != "BETTING":
            return await i.response.send_message("❌ ベット受付時間を過ぎています！", ephemeral=True)
        
        if any(p.user.id == i.user.id for p in self.view.players):
            return await i.response.send_message("❌ 既にベット済みです。", ephemeral=True)

        # 1. 入力値の解析
        user_input = self.bet_input.value.strip().lower()
        is_test = (user_input == "test")
        
        # 2. ベット額の確定
        if is_test:
            bet_amt = 0
        else:
            try:
                bet_amt = int(user_input)
                if bet_amt <= 0: raise ValueError
            except ValueError:
                return await i.response.send_message("❌ 正しいコイン数を入力してください。", ephemeral=True)

        # 3. 自動利確設定の解析
        auto_val = self.auto_input.value.strip()
        auto_cashout_at = None
        if auto_val:
            try:
                auto_cashout_at = round(float(auto_val), 2)
                if auto_cashout_at <= 1.0: return await i.response.send_message("❌ 1.01x以上で指定してください。", ephemeral=True)
            except ValueError:
                return await i.response.send_message("❌ 倍率は数字で入力してください。", ephemeral=True)

        # 4. コイン消費とランク処理（非テスト時のみ）
        rank_emb = None
        if not is_test:
            res = self.view.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
            current_coins = res.data[0].get('coin_count', 0) if res.data else 0
            if current_coins < bet_amt:
                return await i.response.send_message(f"❌ コインが足りません！ (所持: {current_coins:,}枚)", ephemeral=True)

            # DB更新
            self.view.bot.supabase.table("user_coins").update({"coin_count": current_coins - bet_amt}).eq("user_id", str(i.user.id)).execute()
            
            # ランク処理 (ベット額確定・コイン消費後に行う)
            rank_emb = await process_rank_system(self.view.bot, i.user.id, bet_amt)

        # 5. プレイヤー登録
        player_obj = CrashPlayer(i.user, bet_amt, auto_cashout_at)
        self.view.players.append(player_obj)

        # 6. メッセージ送信
        msg = f"🧪 **テストモード**" if is_test else f"✅ **{bet_amt:,}枚**"
        if auto_cashout_at: msg += f"（🤖自動: `{auto_cashout_at:.2f}x`）"
        msg += " でゲームに参加しました！\n\n⚠️ **【注意】** 画面更新がカクつくことがありますが、内部処理は正確に行われます。"

        await i.response.send_message(content=msg, embed=rank_emb, ephemeral=True)
        await self.view.update_panel_message()


# --- 🎮 メイン常駐ゲームView（全自動ループ仕様） ---
class CrashGameView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.players = []
        self.game_phase = "BETTING"
        self.current_multiplier = 1.00
        self.crash_point = 1.00
        self.countdown_seconds = 20
        self.message = None
        self.is_looping = False
        self.history = []

    def generate_embed(self):
        if self.history:
            history_str = " | ".join(f"`{h:.2f}x`" for h in self.history)
        else:
            history_str = "*まだ履歴がありません*"

        if self.game_phase == "BETTING":
            emb = discord.Embed(title="🚀 クラッシュ（Crash）- 受付中", color=0x3498db)
            emb.description = f"# ⏰ 次のラウンドまで あと **{self.countdown_seconds} 秒**\n\n画面がクラッシュ（爆発）する前に利確してコインを増やせ！\n下の「💸 ベットする」ボタンから参加登録してね。"
            
            p_str = ""
            for p in self.players:
                tag = " [🧪TEST]" if p.bet_amount == 0 else ""
                auto_tag = f" (🤖自動:{p.auto_cashout_at:.2f}x)" if p.auto_cashout_at else ""
                p_str += f"• **{p.user.display_name}**: {p.bet_amount:,} 枚{tag}{auto_tag}\n"
            emb.add_field(name="👥 参加中のプレイヤー", value=p_str if p_str else "*待機中...*", inline=False)
            emb.add_field(name="📜 直近の結果（過去10回）", value=history_str, inline=False)
            return emb

        elif self.game_phase == "RUNNING":
            emb = discord.Embed(title="📈 クラッシュ - 上昇中！！！", color=0xf1c40f)
            emb.description = f"# 🚀 **[ {self.current_multiplier:.2f}x ]**\n\nぶっ飛ぶ前に下の「🟢 キャッシュアウト」を押せ！"
            
            status_str = ""
            for p in self.players:
                tag = " (🧪TEST)" if p.bet_amount == 0 else ""
                auto_tag = f" [🤖目安:{p.auto_cashout_at:.2f}x]" if p.auto_cashout_at and not p.cashed_out else ""
                if p.cashed_out:
                    status_str += f"✅ **{p.user.display_name}**: **{p.payout_multiplier:.2f}x** で利確 (+{p.profit:,}枚){tag}\n"
                else:
                    current_profit = 0 if p.bet_amount == 0 else int(p.bet_amount * self.current_multiplier) - p.bet_amount
                    status_str += f"🏃‍♂️ **{p.user.display_name}**: 未利確 (現在: +{current_profit:,}枚){tag}{auto_tag}\n"
            emb.add_field(name="📊 プレイヤー状況", value=status_str, inline=False)
            emb.add_field(name="📜 直近の結果（過去10回）", value=history_str, inline=False)
            return emb

        elif self.game_phase == "CRASHED":
            emb = discord.Embed(title="💥💥 爆発（クラッシュ） 💥💥", color=0xe74c3c)
            emb.description = f"# 💥 **{self.crash_point:.2f}x** でクラッシュしました！\n\nまもなく次のラウンドの受付が始まります..."
            
            status_str = ""
            for p in self.players:
                tag = " [🧪TEST]" if p.bet_amount == 0 else ""
                if p.cashed_out:
                    status_str += f"💰 **{p.user.display_name}**: **+{p.profit:,}枚** 獲得！({p.payout_multiplier:.2f}x){tag}\n"
                else:
                    status_str += f"💀 **{p.user.display_name}**: ロスト ( -{p.bet_amount:,}枚 ){tag}\n"
            emb.add_field(name="🏁 最終結果", value=status_str if status_str else "*参加者なし*", inline=False)
            emb.add_field(name="📜 直近の結果（過去10回）", value=history_str, inline=False)
            return emb

    def update_buttons(self):
        self.clear_items()
        if self.game_phase == "BETTING":
            self.add_item(Button(label="💸 ベットする / テスト", style=discord.ButtonStyle.primary, custom_id="crash_main_bet"))
        elif self.game_phase == "RUNNING":
            any_cashed_out = any(p.cashed_out for p in self.players)
            if any_cashed_out:
                self.add_item(Button(label="🎉 利確者あり！継続中...", style=discord.ButtonStyle.premium, custom_id="crash_main_cashout"))
            else:
                self.add_item(Button(label="🟢 キャッシュアウト（利確）", style=discord.ButtonStyle.success, custom_id="crash_main_cashout"))
        elif self.game_phase == "CRASHED":
            pass

    async def update_panel_message(self):
        if self.message:
            self.update_buttons()
            try:
                await self.message.edit(embed=self.generate_embed(), view=self)
            except: pass

    def calculate_crash_point(self):
        if random.random() < 0.03: return 1.00
        hash_val = random.randint(0, 10000000)
        if hash_val % 50 == 0: return round(random.uniform(5.0, 77.0), 2)
        return round(98 / (100 - random.uniform(0, 98)), 2)

    async def start_auto_loop(self):
        if self.is_looping: return
        self.is_looping = True

        while True:
            # 1. ベット受付フェーズ
            self.game_phase = "BETTING"
            self.players = []
            self.countdown_seconds = 20
            
            while self.countdown_seconds > 0:
                await self.update_panel_message()
                await asyncio.sleep(2)
                self.countdown_seconds -= 2
            
            # 2. ゲーム上昇フェーズ
            self.game_phase = "RUNNING"
            self.current_multiplier = 1.00
            self.crash_point = self.calculate_crash_point()
            if self.crash_point < 1.00: self.crash_point = 1.00

            while self.current_multiplier < self.crash_point:
                for _ in range(10):
                    await asyncio.sleep(0.1)

                    self.current_multiplier += round(random.uniform(0.005, 0.015), 3)

                    # 🤖 【自動キャッシュアウト】判定
                    for p in self.players:
                        if not p.cashed_out and p.auto_cashout_at and self.current_multiplier >= p.auto_cashout_at:
                            if p.auto_cashout_at <= self.crash_point:
                                p.cashed_out = True
                                p.payout_multiplier = p.auto_cashout_at
                                
                                if p.bet_amount > 0:
                                    total_return = int(p.bet_amount * p.payout_multiplier)
                                    p.profit = total_return - p.bet_amount
                                    
                                    res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(p.user.id)).execute()
                                    c_coins = res.data[0].get('coin_count', 0) if res.data else 0
                                    self.bot.supabase.table("user_coins").update({"coin_count": c_coins + total_return}).eq("user_id", str(p.user.id)).execute()

                    if self.current_multiplier >= self.crash_point: break
                
                if self.current_multiplier >= self.crash_point: 
                    break
                await self.update_panel_message()

            # 3. クラッシュ（終了）フェーズ
            self.current_multiplier = self.crash_point
            self.game_phase = "CRASHED"
            
            self.history.insert(0, self.crash_point)
            if len(self.history) > 10:
                self.history.pop()

            await self.end_game_round()
            await asyncio.sleep(5)

    async def end_game_round(self):
        await self.update_panel_message()

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        history_channel = self.bot.get_channel(RESULT_HISTORY_CHANNEL_ID)
        
        has_winner = any(p.cashed_out for p in self.players)
        embed_color = 0xf1c40f if has_winner else 0xe74c3c
        embed_title = "💛 クラッシュ結果（利確成功あり）" if has_winner else "💔 クラッシュ結果（全員敗北・不参加）"

        public_emb = discord.Embed(title=embed_title, color=embed_color, timestamp=datetime.datetime.now())
        public_emb.description = f"**最終クラッシュポイント:** `{self.crash_point:.2f}x`"
        
        res_str = ""
        for p in self.players:
            tag = " [🧪TEST]" if p.bet_amount == 0 else ""
            if p.cashed_out: 
                res_str += f"• {p.user.mention}: **+{p.profit:,}枚** ({p.payout_multiplier:.2f}x){tag}\n"
            else: 
                res_str += f"• {p.user.mention}: **-{p.bet_amount:,}枚** ロスト{tag}\n"
        
        if res_str:
            public_emb.add_field(name="📝 参加者損益一覧", value=res_str, inline=False)
            if log_channel: await log_channel.send(embed=public_emb)
            if history_channel: await history_channel.send(embed=public_emb)


# --- ⚙️ ② 全体管理システムCog ---
class CrashGameSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}

    @app_commands.command(name="crash_panel", description="【管理者専用】常時全自動ループ型クラッシュパネルを設置します")
    @commands.has_permissions(administrator=True)
    async def spawn_crash_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        view = CrashGameView(self.bot)
        panel_msg = await interaction.channel.send(embed=view.generate_embed(), view=view)
        view.message = panel_msg
        
        self.active_games[interaction.channel_id] = view
        await interaction.followup.send("✅ 全自動ループ型クラッシュゲームパネルを設置しました！", ephemeral=True)
        asyncio.create_task(view.start_auto_loop())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "") if interaction.data else None
        if not custom_id: return

        channel_id = interaction.channel_id
        view = self.active_games.get(channel_id)
        if not view: return

        if custom_id == "crash_main_bet":
            if view.game_phase != "BETTING":
                return await interaction.response.send_message("❌ 現在はベット受付時間外です。", ephemeral=True)
            await interaction.response.send_modal(CrashBetModal(view))

        elif custom_id == "crash_main_cashout":
            if view.game_phase != "RUNNING":
                return await interaction.response.send_message("❌ 現在ゲームは動いていません。", ephemeral=True)

            player = next((p for p in view.players if p.user.id == interaction.user.id), None)
            if not player:
                return await interaction.response.send_message("❌ このラウンドに参加していません。", ephemeral=True)
            if player.cashed_out:
                return await interaction.response.send_message("❌ 既にキャッシュアウト済みです。", ephemeral=True)

            player.cashed_out = True
            player.payout_multiplier = view.current_multiplier
            
            if player.bet_amount > 0:
                total_return = int(player.bet_amount * player.payout_multiplier)
                player.profit = total_return - player.bet_amount

                res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(interaction.user.id)).execute()
                c_coins = res.data[0].get('coin_count', 0) if res.data else 0
                self.bot.supabase.table("user_coins").update({"coin_count": c_coins + total_return}).eq("user_id", str(interaction.user.id)).execute()
                await interaction.response.send_message(f"💰 利確成功！ `{player.payout_multiplier:.2f}x` / +{player.profit:,}枚", ephemeral=True)
            else:
                player.profit = 0
                await interaction.response.send_message(f"🧪 **テスト利確成功！** `{player.payout_multiplier:.2f}x` (コインの変動なし)", ephemeral=True)
                
            await view.update_panel_message()

async def setup(bot):
    await bot.add_cog(CrashGameSystem(bot))